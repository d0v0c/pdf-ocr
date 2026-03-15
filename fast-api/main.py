# 直接用 Gemini API 识别
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form
from fastapi.responses import FileResponse
from pypdf import PdfReader, PdfWriter
import io
import math
import json
import re
import uvicorn
from reportlab.pdfgen import canvas
import asyncio
from datetime import datetime, timedelta, timezone
from config import settings
from pathlib import Path
from google import genai
from google.genai import types

GOOGLE_API_KEY_FREE = settings.google_api_key_free
GOOGLE_API_KEY_PAID = settings.google_api_key_paid
client_free = genai.Client(api_key=GOOGLE_API_KEY_FREE)
client_paid = genai.Client(api_key=GOOGLE_API_KEY_PAID)

TEMP_PDF = Path("./temp_pdfs").resolve()
TEMP_PDF.mkdir(parents=True, exist_ok=True)

PROMPTS = {
    0: """
        Analyze the PDF and extract the following details into a JSON object.
        
        Extraction Rules:
        1. contract_id: Extract the "Seller contract No" (above the table).
        2. item_table: Parse the table.
           - Exclude the header row: Ignore the row containing column names such as "Name", "Quantity", "Net Price" at the top of table.
           - Ignore the bottom summary row that spans across all columns.
           - Extract each content row as an array: [No, Name, Name of commodity and specification, Quantity, Net Price, Total net price, Remark].
           - Handling Blank Cells: If a cell is originally empty, put "" in it.
           - Handling Vertical Merged Cells: If a cell spans multiple rows, repeat the value in each corresponding row.
           - Format: Pipe-separated Markdown table, a SINGLE STRING containing the entire table.
        3. total_value: Extract the "Total value" (below the table).
        4. address: Extract the content text from clause "5. Form of shipment and destination".
        5. box_2d: Find the bounding box for "working days" at the right bottom. Return [ymin, xmin, ymax, xmax].
        
        Output Format:
        Return strictly valid JSON. Keep the extracted content original (Chinese).
        """,
    1: """
        Analyze the PDF and extract the following details into a JSON object.
        1. customer_name: Extract the "最终用户名称" at the bottom. If it is empty, return "未知".
        2. box_2d: Find the bounding box for "The Company" at the right bottom under "Buyer". Return [ymin, xmin, ymax, xmax].
        Return strictly valid JSON. Keep the extracted content original (Chinese).
        """,
    "default": """
        Analyze the PDF and extract the following details into a JSON object.
        box_2d: Find the bounding box of the bottom-most text located in the right side of the page. 
            - Exclude Footers: Ignore page numbers, technical markers or company info at the very bottom edge.
            - Avoid Occlusion: The text must be not overlapped by any stamp or seal.
            - Clearance: There must be a vertical or horizontal gap (at least 10% of the page width) between this text and existing stamp. If the text is too close to the stamp, choose a text a little bit up or right.
            - Output: Return the result as box_2d in [ymin, xmin, ymax, xmax].
        Return strictly valid JSON. Keep the extracted content original (Chinese).
        """
}

app = FastAPI(
    docs_url=None,    # 关闭 /docs (Swagger UI)
    redoc_url=None,   # 关闭 /redoc (ReDoc)
    openapi_url=None, # 关闭 /openapi.json
    debug=False
)
# app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.png")

@app.get("/ppp-ddd-fff")
async def index():
    return FileResponse('static/index.html')

@app.get("/api/pdf-download/{filename}")
def download_pdf(filename: str, background_tasks: BackgroundTasks):
    file_path = TEMP_PDF / filename
    if not file_path.exists():
        return {"error": "文件不存在或已过期"}

    # FastAPI 会在响应发送完毕后，执行这个函数
    background_tasks.add_task(remove_file, file_path)

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/pdf"
    )


@app.post("/api/pdf-extract")
async def extract_pdf(file: UploadFile = File(...), is_paid: str = Form(...)):
    print(f"接收到的模式: {is_paid}")  # 输出: "paid" 或 "free"
    if is_paid == "paid":
        current_client = client_paid
    else:
        current_client = client_free

    # 验证文件
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="PDF 过大，不能超过 10MB")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="不是 PDF 文件")
    try:
        reader = PdfReader(file.file)
    except Exception:
        raise HTTPException(status_code=400, detail="文件损坏或无法读取")
    if len(reader.pages) < 2:
        raise HTTPException(status_code=400, detail="PDF 只有一页")


    # 识别 pyPDF，分页提取 PDF
    tasks = []
    for i, page in enumerate(reader.pages):
        p_bytes = pdf_page_to_bytes(page)
        tasks.append(call_gemini(p_bytes, i, current_client))

    results_list = await asyncio.gather(*tasks)


    # 提取
    contract_id = results_list[0].get('contract_id')
    item_table = parse_markdown_table(results_list[0].get("item_table"))
    total_value = to_clean_float(results_list[0].get('total_value'))
    address = results_list[0].get('address')
    customer_name = results_list[1].get('customer_name')
    box_2d_list = [res.get('box_2d') for res in results_list]


    # 处理一下需要特殊处理的字符
    is_value_correct = "总价正确"
    err_subtotal = ''
    computed_value = 0.0
    for i, item in enumerate(item_table):
        # 把NM后面的O改成0
        item[2] = item[2].replace('NMO', 'NM0')
        item[3] = to_clean_int(item[3])
        item[4] = to_clean_float(item[4])
        item[5] = to_clean_float(item[5])
        if not math.isclose(item[5], item[3] * item[4], abs_tol=0.01):
            err_subtotal += f" {i}"
            is_value_correct = f"总价错误，小计{err_subtotal} 计算错误"

        computed_value += item[3] * item[4]

    if not math.isclose(computed_value, total_value, abs_tol=0.01):
        is_value_correct = f"总价错误，算出来是 {computed_value}"


    # print(item_table)
    # print(total_value)
    # print(contract_id)
    # print(address)
    # print(f'anchor_upper_top {anchor_upper_top} \t-- {anchor_upper} \t right {anchor_upper_right}')
    # print(f'anchor_lower_top {anchor_lower_top} \t-- {anchor_lower}')
    # 最后拼成一张表格
    final_data = [
        {
            "序号": row[0],
            "合同编号": contract_id,
            "签订日期": "",
            "品名": row[1],
            "产品型号": row[2],
            "数量": row[3],
            "单价": row[4],
            "小计": row[5],
            "总价": total_value,
            "票款": "",
            "最终用户名称": customer_name,
            "占": "",
            "位": "",
            "空": "",
            "白": "",
            "列": "",
            "备注": row[6],
            "地址": address
        }
        for row in item_table
    ]

    # 盖章
    filename = stamp_pdf(reader, contract_id, customer_name, total_value, box_2d_list)

    return {
        "table": final_data,
        "is_value_correct": is_value_correct,
        "filename": filename
    }

def pdf_page_to_bytes(page):
    """PDF 页面转为 二进制文件流"""
    writer = PdfWriter()
    writer.add_page(page)
    # 在内存里准备一个“临时容器”
    temp_buffer = io.BytesIO()
    writer.write(temp_buffer)
    return temp_buffer.getvalue()

def parse_markdown_table(text):
    if not text:
        return []

    rows = []
    lines = text.strip().split('\n')

    for line in lines:
        line = line.strip()

        # 1. 过滤干扰行
        if "---" in line:
            continue
        if "|" not in line:
            continue

        # 2. 核心解析逻辑
        # .strip('|') -> 去掉行首和行尾的 '|' (避免 split 出来空字符串)
        # c.strip()   -> 去掉每个单元格内容的空格 (例如 "  螺丝  " -> "螺丝")
        cells = [c.strip() for c in line.strip('|').split('|')]

        rows.append(cells)

    return rows


async def call_gemini(page: bytes, page_index: int, client: genai.Client):
    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=page, mime_type="application/pdf"),
                PROMPTS.get(page_index, PROMPTS["default"]),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0  # 低温度以保证数据提取的精确性
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"谷歌 AI 报错: {e}")
    if not response.candidates:
        raise HTTPException(status_code=500, detail="模型未返回任何候选结果。")
    candidate = response.candidates[0]
    if candidate.finish_reason != "STOP":
        raise HTTPException(status_code=500, detail=f"模型生成中断。原因: {candidate.finish_reason}")

    return json.loads(response.text)


def to_clean_float(value):
    text = str(value).strip()
    # 用正则只留下数字、小数点
    clean_text = re.sub(r'[^0-9.]', '', text)
    try:
        return float(clean_text)
    except ValueError:
        return 0.0

def to_clean_int(value):
    text = str(value).strip()
    # 用正则只留下数字
    clean_text = re.sub(r'[^0-9]', '', text)
    try:
        return int(clean_text)
    except ValueError:
        return 0

def stamp_pdf(reader: PdfReader, contract_id: str, customer_name: str, total_value: float, box_2d_list: list):
    # 准备印章
    page_width = float(reader.pages[0].mediabox.width)
    page_height = float(reader.pages[0].mediabox.height)

    stamp_width = 110

    writer = PdfWriter()
    stamp_path = settings.STAMP_PATH
    if not stamp_path.is_file():
        raise HTTPException(status_code=500, detail="服务器端印章文件丢失")

    for i, page in enumerate(reader.pages):
        # reportlab 创建一个只包含印章的临时 PDF
        packet = io.BytesIO()

        stamp_x, stamp_y = get_stamp_center(box_2d_list[i], page_width, page_height)
        x_pos = min(stamp_x - stamp_width / 2 + 5, page_width - stamp_width) if i != 0 else min(stamp_x - stamp_width, page_width - stamp_width)
        y_pos = max(stamp_y - stamp_width / 2, 0)

        can = canvas.Canvas(packet, pagesize=(page_width, page_height))
        can.drawImage(
            stamp_path,
            x_pos,
            y_pos,
            width=stamp_width,
            height=stamp_width,
            preserveAspectRatio=True,
            mask='auto'
        )
        can.save()

        # 将印章层合并到原页面
        packet.seek(0)
        stamp_pdf_file = PdfReader(packet)
        stamp_page = stamp_pdf_file.pages[0]
        page.merge_page(stamp_page)

        # 这一页添加到结果
        writer.add_page(page)

    # 输出
    output_buffer = io.BytesIO()
    writer.write(output_buffer)
    output_buffer.seek(0)  # 指针回到开头，以便发送给前端

    # 修改文件名
    # 1. 按照 '/' 分割
    parts = contract_id.split('/')
    contract_sid = parts[0]
    contract_date = parts[1]
    beijing_time = datetime.now(timezone(timedelta(hours=8)))
    date_str = beijing_time.strftime('%Y%m%d')

    filename = f"{date_str}-{contract_sid}-{contract_date}-合同回传-{customer_name or '未知'}-{int(total_value)}.pdf"

    file_path = TEMP_PDF / filename
    with open(file_path, "wb") as f:
        writer.write(f)

    return filename


def get_stamp_center(box_2d, page_width, page_height):
    if not box_2d or len(box_2d) != 4:
        raise HTTPException(status_code=500, detail="无效的 box_2d 数据")

    ymin, xmin, ymax, xmax = box_2d

    center_y_norm = (ymin + ymax) / 2
    center_x_norm = (xmin + xmax) / 2

    # 转换为实际页面尺寸 (X轴)
    final_x = (center_x_norm / 1000) * page_width
    # 转换为实际页面尺寸并翻转 Y 轴 (图片坐标原点在左上，PDF 坐标原点在左下)
    image_y_abs = (center_y_norm / 1000) * page_height
    final_y = page_height - image_y_abs

    return final_x, final_y


def remove_file(path: Path):
    """清理文件的后台任务"""
    try:
        path.unlink(missing_ok=True)
        print(f"已删除临时文件: {path}")
    except Exception as e:
        print(f"删除文件失败: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)