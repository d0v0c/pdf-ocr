"use server";

import fs from "fs/promises";
import path from "path";
import { PDFDocument } from "pdf-lib";
import { GoogleGenAI } from "@google/genai";
import { makeAction } from "@/lib/action-wrapper";
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import { z } from "zod";
import { zodToJsonSchema } from "zod-to-json-schema";

const PROMPTS = `Analyze the PDF and extract the required details. Follow the provided JSON schema structure and its field descriptions. Keep the extracted content in its original language (Chinese).`;

const itemTable = z.array(
    z.object({
        no: z.coerce.number().describe("序号 No, column 0"),
        name: z.string().catch("").describe("名称 Name，column 1"),
        commodity: z.string().catch("").describe("型号/规格 Name of commodity and specification, column 2"),
        quantity: z.coerce.number().describe("数量 Quantity, column 3, extract as a clean number without commas"),
        price: z.coerce.number().describe("含税单价（人民币） Net price (CNY), column 4, extract as a clean number without commas"),
        subTotal: z.coerce.number().describe("总价小计（人民币）Total net price, column 5, extract as a clean number without commas"),
        remark: z.string().catch("").describe("备注 Remark, column 6"),
    })
);
const SchemaPage0 = z.object({
    contractId: z.string().describe(`the "Seller contract" No above the table, also in the header`),
    itemTable: itemTable.describe(
        `the table, ignore the bottom summary row that spans across all columns. 
        If a cell is empty, put "" in it.
        If a cell spans multiple rows, repeat the value in each corresponding row.`
    ),
    totalValue: z.coerce.number().describe(`the "Total value" below the table, extract as a clean number without commas`),
    address: z.string().describe(`the content text from clause "5. Form of shipment and destination"`),
    box2d: z.array(z.number()).describe(
        `find the bounding box for "working days" at the right bottom. 
        Return coordinates in a 0-1000 normalized format as [ymin, xmin, ymax, xmax].
        Example: [800,700,800,760].`),
});
const SchemaPage1 = z.object({
    customerName: z.string().describe(`the "最终用户名称" at the bottom. If it is empty, put "未知" in it`),
    box2d: z.array(z.number()).describe(
        `Find the bounding box for "The Company" at the right bottom located under "Buyer". 
        Return coordinates in a 0-1000 normalized format as [ymin, xmin, ymax, xmax].
        Example: [800,700,800,760].`),
});
const SchemaDefault = z.object({
    box2d: z.array(z.number()).describe(
        `Find the bounding box of the bottom-most text located in the right side of the page. 
        Return coordinates in a 0-1000 normalized format as [ymin, xmin, ymax, xmax].
        Example: [800,700,800,760].
         - Exclude Footers: Ignore page numbers, technical markers or company info at the very bottom edge.
         - Avoid Occlusion: The text must be not overlapped by any stamp or seal.
         - Clearance: There must be a vertical or horizontal gap (at least 10% of the page width) between this text and existing stamp. If the text is too close to the stamp, choose a text a little bit up or right.`),
});
const JSON_SCHEMA: Record<number, z.ZodTypeAny> = {
    0: SchemaPage0,
    1: SchemaPage1,
};

const clientFree = new GoogleGenAI({apiKey: process.env.GOOGLE_API_KEY_FREE});
const clientPaid = new GoogleGenAI({apiKey: process.env.GOOGLE_API_KEY_PAID});
const stampPath = path.resolve(process.cwd(), process.env.STAMP_PATH || "stamp.png");
const TEMP_PDF_DIR = path.resolve(process.cwd(), "temp-pdfs");
fs.mkdir(TEMP_PDF_DIR, { recursive: true }).catch(console.error);

dayjs.extend(utc);
dayjs.extend(timezone);

export const extractPdfAction = makeAction(async ({ file, isPaidMode }: { file: File, isPaidMode: boolean }, setLogPayload) => {
    // console.log(`接收到的模式: ${isPaidMode ? "paid" : "free"}`);
    let log: string = "";
    log += `模式：${isPaidMode ? "paid" : "free"}`;
    // 将 Web File 转为 Node.js Buffer
    // 类似 byte[] bytes = Files.readAllBytes()
    const arrayBuffer = await file.arrayBuffer();

    // 1. 加载 PDF 验证页数
    let pdfDoc: PDFDocument;
    try {
        pdfDoc = await PDFDocument.load(arrayBuffer);
    } catch (e) {
        throw new Error(`文件损坏或无法读取：${e}`);
    }

    const pageCount = pdfDoc.getPageCount();
    if (pageCount < 2) throw new Error("PDF 只有一页");
    log += ` | 页数：${pageCount}`;

    // 2. 分页调用 Gemini
    const aiClient = isPaidMode ? clientPaid : clientFree;

    const tasks = [];
    for (let i = 0; i < pageCount; i++) {
        // 创建一个新文档，把这一页拷进去
        const tempDoc = await PDFDocument.create();
        const [copiedPage] = await tempDoc.copyPages(pdfDoc, [i]);
        tempDoc.addPage(copiedPage);
        const singlePage = await tempDoc.saveAsBase64();

        tasks.push(callGemini(aiClient, singlePage, i));
    }
    // 等待所有页面解析完毕
    const resultsList = await Promise.all(tasks);

    // 3. 提取数据
    const firstPage = resultsList[0] as z.infer<typeof SchemaPage0>;
    const secondPage = resultsList[1] as z.infer<typeof SchemaPage1>;
    const box2dList = resultsList.map(res => res.box2d);
    log += ` | box2d：${JSON.stringify(box2dList)}`;
    // 处理一下需要特殊处理的字符
    firstPage.itemTable.forEach(res => res.commodity.replace("NMO", "NM0"));

    // 4. 组装前端表格数据
    const finalData = firstPage.itemTable.map(row => ({
        "序号": row.no,
        "合同编号": firstPage.contractId,
        "签订日期": "",
        "品名": row.name,
        "产品型号": row.commodity,
        "数量": row.quantity,
        "单价": row.price,
        "小计": row.subTotal,
        "总价": firstPage.totalValue,
        "票款": "",
        "最终用户名称": secondPage.customerName,
        "占": "", "位": "", "空": "", "白": "", "列": "",
        "备注": row.remark,
        "地址": firstPage.address
    }));

    // 5. 给 PDF 盖章并保存到磁盘
    const filename = await stampPdfAndSave(pdfDoc, firstPage.contractId, secondPage.customerName, firstPage.totalValue, box2dList);

    setLogPayload(log);
    return {
        table: finalData,
        filename
    };
});



// 调用大模型
async function callGemini(aiClient: GoogleGenAI, page: string, pageIndex: number) {
    try {
        const result = await aiClient.models.generateContent({
            model: "gemini-2.5-flash",
            // [文件, 提示词]：相当于先给模型看资料，后给提示词。数据需要变成 base64.
            contents: [
                { inlineData: {mimeType: 'application/pdf', data: page }},
                { text: PROMPTS }
            ],
            config: {
                responseMimeType: "application/json",
                responseJsonSchema: zodToJsonSchema(JSON_SCHEMA[pageIndex] ?? SchemaDefault),
                temperature: 0,
            },
        });
        const text = result.text;
        if (typeof text !== 'string') {throw new Error("模型无返回内容");}
        return JSON.parse(text);
    } catch (e) {
        throw new Error(`谷歌 AI 报错: ${e}`);
    }
}

// 盖章并保存到磁盘
async function stampPdfAndSave(
    pdfDoc: PDFDocument,
    contractId: string,
    customerName: string,
    totalValue: number,
    box2dList: number[][]
): Promise<string> {

    let stampImage;
    try {
        const stampBytes = await fs.readFile(stampPath);
        stampImage = await pdfDoc.embedPng(stampBytes); // 嵌入印章图片
    } catch (e) {
        throw new Error(`服务器端印章文件丢失：${e}`);
    }

    const stampWidth = 110;
    const stampHeight = 110;
    const pages = pdfDoc.getPages();

    for (let i = 0; i < pages.length; i++) {
        const page = pages[i];
        const { width: pageWidth, height: pageHeight } = page.getSize();
        const box2d = box2dList[i];
        if (!box2d || box2d.length !== 4) continue;
        const [ymin, xmin, ymax, xmax] = box2d;

        // 计算归一化中心点 (0 - 1000)
        const centerYNorm = (ymin + ymax) / 2;
        const centerXNorm = (xmin + xmax) / 2;

        // Gemini 尺寸 -> 实际页面尺寸
        // X 轴逻辑 (左下角为原点)
        const finalX = (centerXNorm / 1000) * pageWidth;
        const xPos = i === 0
            ? Math.min(finalX - stampWidth, pageWidth - stampWidth)
            : Math.min(finalX - stampWidth / 2 + 5, pageWidth - stampWidth);

        // Y 轴逻辑 (pdf-lib 坐标在左下角，Gemini 在左上)
        // 1. 先算这个点距离顶部的绝对距离
        const distFromTop = (centerYNorm / 1000) * pageHeight;
        // 2. 转换成距离底部的 Y 坐标
        const absoluteY = pageHeight - distFromTop;
        // 3. pdf-lib 画图是从图片的【左下角】开始画的，所以要减去印章高度的一半才能中心对齐
        const yPos = Math.max(absoluteY - stampHeight / 2, 0);

        page.drawImage(stampImage, {
            x: xPos,
            y: yPos,
            width: stampWidth,
            height: stampHeight,
            opacity: 0.9, // 给印章加一点真实的透明度
        });
    }

    // 生成文件名
    const parts = contractId.split('/');
    const contract_sid = parts[0] || "未知编号";
    const contract_date = parts[1] || "";
    // 东八区时间
    const dateStr = dayjs().tz("Asia/Shanghai").format('YYYYMMDD');

    const filename = `${dateStr}-${contract_sid}-${contract_date}-合同回传-${customerName || '未知'}-${Math.floor(totalValue)}.pdf`;

    // 保存到本地磁盘
    const pdfBytes = await pdfDoc.save();
    const filePath = path.join(TEMP_PDF_DIR, filename);
    await fs.writeFile(filePath, pdfBytes);

    return filename;
}