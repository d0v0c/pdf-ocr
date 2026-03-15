# 本地电脑测试 PaddleOCR

from bs4 import BeautifulSoup
from paddleocr import PPStructureV3
from pypdf import PdfReader
import io
from PIL import Image
import numpy as np

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
                extracted_data["shipment_info"] = str(extracted_data["shipment_info"]).replace("5.运输方式及到达站（港）", "").replace("formofshipmentanddestination", "")
                break

    return extracted_data


def main():
    pdf_path = "./a.pdf"

    # pyPDF 提取pdf第一页
    reader = PdfReader(pdf_path)
    if len(reader.pages) < 1:
        print("❌ PDF 是空的！")
        return

    images = reader.pages[0].images
    if len(images) == 0:
        print("❌ 没有图片！")
        return

    # 二进制图片转换成 Numpy 数组
    img_bytes = images[0].data
    image_stream = io.BytesIO(img_bytes)
    pil_img = Image.open(image_stream).convert('RGB')
    img_array_rgb = np.array(pil_img)
    img_array_bgr = img_array_rgb[:, :, ::-1]

    # PaddleOCR 识别
    pipeline = PPStructureV3(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        use_formula_recognition=False,
        # text_recognition_batch_size=8,
        text_detection_model_name='PP-OCRv4_mobile_det',
        text_recognition_model_name='PP-OCRv4_mobile_rec',
        cpu_threads=4,
    )
    output = pipeline.predict(input=img_array_bgr)

    for res in output:
        # res.save_to_json(save_path="output")
        result = extract_structured_data(res)
        print(result)


if __name__ == '__main__':
    main()
