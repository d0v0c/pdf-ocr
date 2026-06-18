import fs from 'fs/promises';
import path from 'path';
import dayjs from "dayjs";
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
dayjs.extend(utc);
dayjs.extend(timezone);

export async function saveLog(level: 'INFO' | 'ERROR', payload: string, duration: number) {
    try {
        const time = dayjs().tz("Asia/Shanghai").format('YYYY-MM-DD HH:mm:ss');
        const logEntry = JSON.stringify({ time, duration, level, payload }) + '\n';

        // 存储到项目根目录的 logs 文件夹下
        const logDir = path.join(process.cwd(), 'logs');
        const logFile = path.join(logDir, `2026-04-02.log`);

        // 确保目录存在
        await fs.mkdir(logDir, { recursive: true }).catch(() => {});
        await fs.appendFile(logFile, logEntry, 'utf-8');
    } catch (e) {
        console.error('Failed to write log:', e);
    }
}