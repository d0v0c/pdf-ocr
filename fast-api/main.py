# Oracle 服务器部署测试 PaddleOCR

import os
os.environ['FLAGS_use_mkldnn'] = '0'
os.environ['FLAGS_use_stride_kernel'] = '0'
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from bs4 import BeautifulSoup
from paddleocr import PPStructureV3
from pypdf import PdfReader
import io
from PIL import Image
import numpy as np
import uvicorn
app = FastAPI(
    docs_url=None,    # 关闭 /docs (Swagger UI)
    redoc_url=None,   # 关闭 /redoc (ReDoc)
    openapi_url=None,  # 关闭 /openapi.json
    debug=False
)

pipeline = PPStructureV3(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            use_formula_recognition=False,
            text_recognition_batch_size=16,
            cpu_threads=4,
            text_detection_model_name='PP-OCRv4_mobile_det',
            text_recognition_model_name='PP-OCRv4_mobile_rec',
        )

@app.get("/ppp-ddd-fff")
async def index():
    return FileResponse('static/index.html')

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/pdfpdfpdfapi")
async def process_pdf(file: UploadFile = File(...)):
    def extract_structured_data(res):
        """
        输入：PaddleOCR 的 output (Python 字典格式)
        输出：包含三个目标数据的字典
        """

        # 1. 找到 ocr_result
        blocks = res['parsing_res_list']

        # 初始化结果容器
        extracted_data = {
            "seller_contract_no": '',
            "table_data": [],
            "shipment_info": ''
        }

        shipment_info_count = 0
        for block in blocks:
            label = block.label
            raw_content = block.content

            # 提取“卖方合同号” (header)
            if label == 'header':
                # 1. 去除所有空格和换行
                clean_text = str(raw_content).replace(" ", "").replace("\n", "").replace("\r", "")

                # 2. 中文锚点匹配
                if "/" in clean_text:
                    extracted_data["seller_contract_no"] = clean_text
                    # 正则，`$`匹配行尾，找连续 "字母/数字/横杠/斜杠"
                    # match = re.search(r'([A-Za-z0-9\-/]+)$', str(raw_content).strip())
                    # if match:
                    #     extracted_data["seller_contract_no"] = match.group(1)

            # 提取表格 (colspan 过滤)
            elif label == 'table':
                soup = BeautifulSoup(raw_content, 'html.parser')
                rows = soup.find_all('tr')

                clean_table = []
                for i, row in enumerate(rows):
                    # 1. 剔除表头
                    if i == 0:
                        continue

                    cells = row.find_all(['td'])
                    if not cells:
                        continue

                    # 2. 剔除合并单元格 (colspan)
                    has_merge = False
                    for cell in cells:
                        if cell.has_attr('colspan'):
                            has_merge = True
                            break

                    if has_merge:
                        continue

                    # 3. 提取数据，去除空格
                    row_data = [cell.get_text(strip=True) for cell in cells]
                    clean_table.append(row_data)

                extracted_data["table_data"] = clean_table

            # 提取“运输方式” (后置数据)
            elif label == 'text' or label == 'paragraph_title':
                # 去除所有空格
                clean_text = str(raw_content).replace(" ", "").replace("\n", "").replace("：", "").replace(":", "").lower()
                # 先拼接，后删除
                if "formofshipment" in clean_text:
                    shipment_info_count += 1
                    if "5.运输方式" in clean_text: shipment_info_count = 2
                    extracted_data["shipment_info"] += clean_text
                elif "5.运输方式" in clean_text:
                    shipment_info_count += 1
                    if "formofshipment" in clean_text: shipment_info_count = 2
                    extracted_data["shipment_info"] += clean_text
                elif shipment_info_count == 1:
                    extracted_data["shipment_info"] += clean_text

                if shipment_info_count == 2:
                    extracted_data["shipment_info"] = str(extracted_data["shipment_info"]).replace(
                        "5.运输方式及到达站（港）", "").replace("formofshipmentanddestination", "")
                    break

        return extracted_data

    # 1. 验证文件类型
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传 PDF 文件")

    try:
        file_content = await file.read()
        if len(file_content) > 100 * 1024 * 1024:  # 10MB
            raise HTTPException(status_code=400, detail="文件太大，不能超过 100MB")

        pdf_stream = io.BytesIO(file_content)
        # pyPDF 提取pdf第一页
        reader = PdfReader(pdf_stream)
        if len(reader.pages) < 1:
            raise HTTPException(status_code=400, detail="PDF 是空的")

        images = reader.pages[0].images
        if len(images) == 0:
            raise HTTPException(status_code=400, detail="没有图片")

        # 二进制图片转换成 Numpy 数组
        img_bytes = images[0].data
        image_stream = io.BytesIO(img_bytes)
        pil_img = Image.open(image_stream).convert('RGB')
        img_array_rgb = np.array(pil_img)
        img_array_bgr = img_array_rgb[:, :, ::-1]

        # PaddleOCR 识别
        output = pipeline.predict(input=img_array_bgr)

        result = {}
        for res in output:
            # res.save_to_json(save_path="output")
            result = extract_structured_data(res)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理 PDF 时出错: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)