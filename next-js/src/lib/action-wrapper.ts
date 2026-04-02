// 异常拦截器，就是高阶函数包一层回调函数，外面写上try-catch，模仿 next-safe-action + Zod，
// 实现 FastAPI 的 `raise HTTPException(status_code=500, detail="错误信息")` 效果

import {saveLog} from "@/lib/logger";
import dayjs from "dayjs";
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import duration from 'dayjs/plugin/duration';
dayjs.extend(utc);
dayjs.extend(timezone);
dayjs.extend(duration);

// 这里的回调函数嵌套回调函数 makeAction(handler(setLogPayload)) 真的看不懂。
// 等于是只暴露了 handler，但是隐藏了 makeAction 和 makeAction。
export function makeAction<T, R>(handler: (input: T, setLogPayload: (payload: string) => void) => Promise<R>) {
    return async (input: T) => {
        const startTime = dayjs();
        let customPayload = "Action executed successfully";
        const setLogPayload = (payload: string) => {
            customPayload = payload;
        };
        try {
            // 正常执行业务逻辑
            const data = await handler(input, setLogPayload);

            const diff = dayjs().diff(startTime);
            const duration = dayjs.duration(diff).asSeconds();
            await saveLog("INFO", customPayload, duration);

            return { success: true as const, data };
        } catch (error: unknown) {
            // 拦截抛出的异常，转化成普通对象给前端
            const diff = dayjs().diff(startTime);
            const duration = dayjs.duration(diff).asSeconds();
            await saveLog("ERROR", String(error), duration);

            if (error instanceof Error) {
                return { success: false as const, error: error.message };
            }
            return { success: false as const, error: String(error) };
        }
    };
}