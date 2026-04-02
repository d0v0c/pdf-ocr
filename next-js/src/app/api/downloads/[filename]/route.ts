import {after, NextRequest, NextResponse} from 'next/server';
import fs from 'fs/promises';
import path from 'path';
import {saveLog} from "@/lib/logger";
import {notFound} from "next/navigation";

export async function GET(request: NextRequest, { params }: { params: Promise<{ filename: string }> }) {
    // 获取请求 URL 中的参数 (/api/downloads/${filename})
    const resolvedParams = await params;
    if (!resolvedParams.filename) {notFound();}
    // 防止目录穿越攻击
    const fileName = path.basename(decodeURIComponent(resolvedParams.filename));

    // 读取文件
    const filePath = path.resolve(process.cwd(), 'temp-pdfs', fileName);
    let fileBuffer: Buffer;
    try {
        fileBuffer = await fs.readFile(filePath);
    } catch (e) {
        return new NextResponse(`File expired or invalid: ${e}`, { status: 410 }); // 410 Gone 比 404 更符合阅后即焚的语义
    }

    // 后台清理任务 (等同于 FastAPI BackgroundTasks)
    after(async () => {
        try {
            await fs.unlink(filePath); // 等同于 pathlib.unlink
            await saveLog("INFO", `清除文档成功: ${fileName}`, 0);
        } catch (e) {
            await saveLog("ERROR", `清除失败：${e}`, -1);
        }
    });

    return new NextResponse(new Uint8Array(fileBuffer), {
        headers: {
            'Content-Type': 'application/pdf',
            // attachment 表示强制下载，不然浏览器可能会尝试预览
            'Content-Disposition': `attachment; filename="${encodeURIComponent(fileName)}"`,
            // 额外加上缓存控制，不让浏览器或 CDN 缓存这个一次性请求
            'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
        },
    });
}