# 直接用 Baidu API 识别
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pypdf import PdfReader, PdfWriter
import base64
import requests
import io
import os
import math
import json
import re
import uvicorn
import time
from reportlab.pdfgen import canvas
import asyncio
import httpx
from datetime import datetime, timedelta, timezone

API_KEY = os.getenv("BAIDU_API_KEY")
SECRET_KEY = os.getenv("BAIDU_SECRET_KEY")
TEMP_PDF = "./temp_pdfs"

app = FastAPI(
    docs_url=None,    # 关闭 /docs (Swagger UI)
    redoc_url=None,   # 关闭 /redoc (ReDoc)
    openapi_url=None,  # 关闭 /openapi.json
    debug=False
)
# app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/ppp-ddd-fff")
async def index():
    return FileResponse('static/index.html')

@app.get("/api/pdf-download/{filename}")
def download_pdf(filename: str, background_tasks: BackgroundTasks):
    file_path = os.path.join(TEMP_PDF, filename)
    if not os.path.exists(file_path):
        return {"error": "文件不存在或已过期"}

    # FastAPI 会在响应发送完毕后，执行这个函数
    background_tasks.add_task(remove_file, file_path)

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/pdf"
    )


@app.post("/api/pdf-extract")
async def extract_pdf(file: UploadFile = File(...)):
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
    # pyPDF 提取pdf第一页
    p1_base64 = pdf_page_to_base64(reader.pages[0])
    p2_base64 = pdf_page_to_base64(reader.pages[1])

    # 识别
    timeout_config = httpx.Timeout(60.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout_config) as client:
        task1 = call_baidu_ocr(client, p1_base64, {'recg_tables': 'true'})
        task2 = call_baidu_ocr(client, p2_base64, {})

        # asyncio.gather 同时发射 task1 和 task2 请求并等待结果
        data, data2 = await asyncio.gather(task1, task2)

    # 提取
    contract_id = ''
    item_table = []
    total_value = 0.0
    address = ''
    customer_name = ''

    # with open('./b-baidu.json', 'r') as f:
    #     data_str = f.read()
    #     data = json.loads(data_str)
    # with open('./b-baidu2.json', 'r') as f:
    #     data2_str = f.read()
    #     data2 = json.loads(data2_str)

    results = data2['results']
    for i, item in enumerate(results):
        text = item['words']['word']
        if "最终用户名称" in text:
            customer_name = str(text).split('：')[-1].strip()
            if not customer_name and i + 1 < len(results):
                customer_name = results[i + 1]['words']['word'].strip()
            break

    # 从 tables_result 提取 item_table、total_value
    table_body = data['tables_result'][0]['body']
    temp_row = []
    for cell in table_body:
        # 过滤表头
        if cell['row_start'] == 0:
            continue
        # 过滤表尾，提取 total_value
        elif cell['col_end'] - cell['col_start'] > 1:
            total_value_str = str(cell['words']).split('\n')[-1]
            match = re.search(r'[\d,]+\.\d{2}', total_value_str)
            if match: total_value = float(match.group().replace(',', ''))
            item_table.append(temp_row)
        # 碰到第一列，就把这一行放入二维数组
        elif cell['col_start'] == 0 and cell['row_start'] > 1:
            item_table.append(temp_row)
            temp_row = [cell['words']]
        # 碰到普通格，就慢慢拼成一行
        else:
            temp_row.append(cell['words'].replace('\n', ' '))

    # 从 results 提取 contract_id、address
    anchor_upper = ''
    anchor_upper_top = 0
    anchor_upper_right = 0
    anchor_lower = ''
    anchor_lower_top = 0
    doc_body = data['results']
    for item in doc_body:
        text = item['words']['word']
        # contract_id 在页面上方，包含"/"
        if (item['words']['words_location']['top'] < 100) and ("/" in text):
            contract_id = text
        elif "运输方式及到达站" in text:
            loc = item['words']['words_location']
            anchor_upper_top = loc['top']
            anchor_upper_right = loc['left'] + loc['width']
            anchor_upper = text
        elif "shipment" in text:
            anchor_lower_top = item['words']['words_location']['top']
            anchor_lower = text
    # if anchor_upper != '' and anchor_lower != '':
    #     for item in doc_body:
    #         loc = item['words']['words_location']
    #         # address 比`运输方式`低，比`shipment`高，在`运输方式`右边
    #         if (loc['top'] > anchor_upper_top - 5) and (loc['top'] < anchor_lower_top + 5):
    #             if anchor_upper_right < loc['left']:
    #                 address = item['words']['word']
                    # print(f"address_top {loc['top']} \t-- {address} left {loc['left']}")

    matched_parts = []  # 用于暂时存储符合条件的片段
    if anchor_upper != '' and anchor_lower != '':
        for item in doc_body:
            loc = item['words']['words_location']
            # 保持原有的位置判断逻辑
            # address 比`运输方式`低，比`shipment`高
            if (loc['top'] > anchor_upper_top - 5) and (loc['top'] < anchor_lower_top + 5):
                # 在`运输方式`右边
                if anchor_upper_right < loc['left']:
                    # 将文本和其左边距(用于排序)作为一个字典存入列表
                    matched_parts.append({
                        "text": item['words']['word'],
                        "top": loc['top']
                    })
    # 处理收集到的片段
    if matched_parts:
        # 1. 排序：根据 'left' 坐标从小到大排序（从左到右阅读习惯）
        matched_parts.sort(key=lambda x: x['top'])
        # 2. 拼接：将所有文本提取出来拼接在一起
        # 注意：如果单词之间需要空格，请将 "" 改为 " "
        address = "".join([part['text'] for part in matched_parts])
        print(f"提取到的完整地址: {address}")


    if address == '':
        address = anchor_upper + anchor_lower
        address = address.replace(' ', '').replace(':', '').replace('：', '').replace('5.运输方式及到达站（港）', '').replace('Formofshipmentanddestination', '')

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
            "占位1": "",
            "占位2": "",
            "占位3": "",
            "占位4": "",
            "占位5": "",
            "备注": row[6],
            "地址": address
        }
        for row in item_table
    ]

    # 盖章
    filename = stamp_pdf(reader, contract_id, customer_name, total_value)

    return {
        "table": final_data,
        "is_value_correct": is_value_correct,
        "filename": filename
    }

def pdf_page_to_base64(page_obj):
    """PDF 页面转为 Base64 字符串"""
    writer = PdfWriter()
    writer.add_page(page_obj)
    # 在内存里准备一个“临时容器”
    with io.BytesIO() as temp_buffer:
        writer.write(temp_buffer)
        b64_str = base64.b64encode(temp_buffer.getvalue()).decode("utf-8")
    return b64_str


async def call_baidu_ocr(client: httpx.AsyncClient, base64_content: str, extra_params: dict = None):
    url = "https://aip.baidubce.com/rest/2.0/ocr/v1/doc_analysis_office"
    params = {"access_token": get_access_token()}  # access_token 建议放在 URL 参数里
    data = {
        'pdf_file': base64_content,
        'erase_seal': 'true'
    }
    if extra_params:
        data.update(extra_params)

    response = await client.post(url, params=params, data=data)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=f"百度 API 报错: {response.text}")

    return response.json()

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

def stamp_pdf(reader: PdfReader, contract_id: str, customer_name: str, total_value: float):
    # 准备印章
    stamp_width = 120
    margin_right = 100
    margin_bottom = 100

    writer = PdfWriter()
    stamp_path = "./stamp.png"
    if not os.path.exists(stamp_path):
        raise HTTPException(status_code=500, detail="服务器端印章文件丢失")

    for page in reader.pages:
        # reportlab 创建一个只包含印章的临时 PDF
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=(page_width, page_height))

        x_pos = page_width - stamp_width - margin_right
        y_pos = margin_bottom

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
        stamp_pdf = PdfReader(packet)
        stamp_page = stamp_pdf.pages[0]
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

    file_path = os.path.join(TEMP_PDF, filename)
    with open(file_path, "wb") as f:
        writer.write(f)

    return filename


def remove_file(path: str):
    """清理文件的后台任务"""
    try:
        os.remove(path)
        print(f"已删除临时文件: {path}")
    except Exception as e:
        print(f"删除文件失败: {e}")


# token 缓存
token_cache = {
    "access_token": "token",
    "expires_at": 0.0
}
def get_access_token():
    """获取 AK，SK 生成的鉴权签名（Access Token）"""
    curr_time = time.time()
    if curr_time < token_cache['expires_at'] - 3600:
        print('没刷新token')
        return token_cache['access_token']
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {"grant_type": "client_credentials", "client_id": API_KEY, "client_secret": SECRET_KEY}
    res = requests.post(url, params=params).json()
    token_cache['access_token'] = str(res.get("access_token"))
    token_cache['expires_at'] = curr_time + float(res.get("expires_in"))
    print(f"刷新token，截至{token_cache['expires_at']}")
    return token_cache['access_token']

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)