"use client";
// 扩展声明 Window 接口，等待 lib.dom.d.ts 更新
// declare global {                        // 声明全局接口 Window
//   interface Window {                    // 声明接口 Window
//     showSaveFilePicker?: (options?: {   // 可选属性 showSaveFilePicker，类型为函数 (options) => Promise
//       suggestedName?: string;
//       types?: Array<{ description: string; accept: Record<string, string[]> }>; // 例如 types: [{ description: "PDF Document", accept: { "application/pdf": [".pdf"] } }]
//     }) => Promise<FileSystemFileHandle>; // 要加 await，相当于 CompletableFuture
//   }
// }
// interface FileSystemFileHandle {
//   createWritable(): Promise<FileSystemWritableFileStream>; // 相当于 new FileOutputStream(file)
// }
// interface FileSystemWritableFileStream {
//   write(data: Blob): Promise<void>;                        // 相当于 outputStream.write(bytes)，Binary Large Object（二进制文件）
//   close(): Promise<void>;                                  // 相当于 outputStream.close()
// }

// 采用 shadcn.com组件库、motion.dev动画、animate-ui.com图标动画、motion-primitives.com文字特效、react-dropzone 钩子
import {useState, useMemo, useCallback, useTransition} from "react";
import {toast} from "sonner"
import {Switch} from "@/components/ui/switch"
import {Label} from "@/components/ui/label"
import {Button} from "@/components/ui/button";
import {cn} from "@/lib/utils";
import {motion, AnimatePresence} from "motion/react"
import {Check} from "@/components/animate-ui/icons/check";
import {TextMorph} from '@/components/ui/text-morph';
import {Clipboard} from "@/components/animate-ui/icons/clipboard";
import {useDropzone} from 'react-dropzone';
import {CloudUpload} from "@/components/animate-ui/icons/cloud-upload";
import {LoaderCircle} from "@/components/animate-ui/icons/loader-circle";
import {extractPdfAction} from "@/actions/extract-pdf";

export default function Main() {
    const [isPaidMode, setIsPaidMode] = useState(false);
    const [isUploading, startUploading] = useTransition();
    const [isHovered, setIsHovered] = useState(false);
    const [isCopied, setIsCopied] = useState(false);

    // 核心表格数据：用数组存储，每一行是一个对象 (Record)
    const [headers, setHeaders] = useState<string[]>([]);
    const [tableData, setTableData] = useState<Record<string, string>[]>([]);
    // 要隐藏的列
    const hiddenColumns = ["签订日期", "票款", "占", "位", "空", "白", "列"];
    const visibleHeaders = headers.filter(h => !hiddenColumns.includes(h));

    // 1. 拖拽上传逻辑
    // useDropzone 的回调函数，接收文件数组
    const onDrop = useCallback(async (acceptedFiles: File[]) => {
        if (acceptedFiles.length === 0) return;
        const file = acceptedFiles[0];

        startUploading(async () => {
            // 调用 Server Action，就像调用本地普通异步函数一样
            const result = await extractPdfAction({file, isPaidMode});
            if (!result.success) {
                toast.error(`提取失败。${result.error}`, {
                    position: "top-center",
                    duration: Infinity,
                    closeButton: true});
                return;
            }
            const data = result.data;
            if (data && data.table && data.table.length > 0) {
                const extractedHeaders = Object.keys(data.table[0]);
                setHeaders(extractedHeaders);
                // 将所有值转为字符串，方便 Input 编辑
                const formattedData = data.table.map((row) => {
                    const newRow: Record<string, string> = {};
                    extractedHeaders.forEach(h => newRow[h] = String(row[h as keyof typeof row]));
                    return newRow;
                });
                setTableData(formattedData);

                // 触发下载逻辑
                if (data.filename) {
                    await triggerDownload(data.filename);
                }
            }
        });
    }, [isPaidMode]);

    // react-dropzone 核心 Hook，取出 react-dropzone 关键函数
    const {getRootProps, getInputProps, isDragActive, isDragReject} = useDropzone({
        onDrop,
        accept: {'application/pdf': ['.pdf']},   // 严格限制只收 PDF
        maxFiles: 1,                             // 每次只能传 1 个
        disabled: isUploading                    // 上传中直接锁死整个组件，防止重复投递
    });

    // IIFE 立即执行函数。渲染前定义样式
    const uiState = (() => {
        // 状态 1：正在上传 (冻结样式)
        if (isUploading) return {
            wrapperClass: "border-slate-300 bg-slate-50 text-blue-600 opacity-50 cursor-not-allowed",
            icon: <LoaderCircle animateOnView className="h-12 w-12" />,
            title: "正在解析 PDF...",
        };
        // 状态 2：拖错文件了 (红色警告)
        if (isDragReject) return {
            wrapperClass: "border-red-400 bg-red-50 text-red-600",
            icon: <CloudUpload animate={isDragReject} className="h-12 w-12" />,
            title: "只支持 PDF，一次上传一个",
        };
        // 状态 3：拖入文件，准备松手 (蓝色高亮)
        if (isDragActive) return {
            wrapperClass: "border-blue-500 bg-blue-50 text-blue-600",
            icon: <CloudUpload animate={isDragActive} className="h-12 w-12" />,
            title: "松开上传",
        };
        // 状态 4：默认状态
        return {
            wrapperClass: "border-slate-300 bg-slate-50 text-slate-600 hover:border-blue-400 hover:bg-slate-100",
            icon: <CloudUpload animate={isHovered} className="h-12 w-12 text-slate-500" />,
            title: "点击 或 将 PDF 拖拽至此上传",
        };
    })();

    // 下载
    const triggerDownload = async (filename: string) => {
        const url = `/api/downloads/${filename}`;
        // try {
        //   // 尝试现代 API
        //   if (window.showSaveFilePicker) {
        //     const handle = await window.showSaveFilePicker({
        //       suggestedName: filename,
        //       types: [{ description: "PDF Document", accept: { "application/pdf": [".pdf"] } }],
        //     });
        //     const resp = await fetch(url);
        //     const blob = await resp.blob();
        //     const writable = await handle.createWritable();
        //     await writable.write(blob);
        //     await writable.close();
        //     return;
        //   }
        // } catch (e) {}

        // 传统下载
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    // 2. 校验价格 (因为有 isRowError 这种由 State 数据计算出的 computed 数据，所以用 useMemo)
    const validation = useMemo(() => {
        // useMemo 在 useEffect 运行之前就执行了
        if (tableData.length === 0) return {rowErrors: 0, isTotalError: false, validatedData: []};

        let rowErrors = 0;
        let calculatedTotalSum = 0;

        const parseNum = (str: string) => {
            const num = parseFloat(str.replace(/[^\d.-]/g, ""));
            return isNaN(num) ? 0 : num;
        };

        const validatedData = tableData.map((row) => {
            // 逐行校验
            let isRowError = false;
            const qty = parseNum(row["数量"]);
            const price = parseNum(row["单价"]);
            const sub = parseNum(row["小计"]);

            if (Math.abs(qty * price - sub) > 0.05) {
                isRowError = true;
                rowErrors++;
            }
            calculatedTotalSum += sub

            return {
                rowData: row,
                isRowError
            };
        });

        // 整体校验
        let isTotalError = false;
        const displayTotal = parseNum(tableData[0]["总价"]);

        if (Math.abs(calculatedTotalSum - displayTotal) > 0.05) {
            isTotalError = true;
        }

        return {rowErrors, isTotalError, validatedData};
    }, [tableData]);

    // 3. 修改单元格
    const updateCell = (rowIndex: number, header: string, value: string) => {
        setTableData(prev => {
            const newData = [...prev];
            // 同步更新所有行的“总价”
            if (header === "总价") {
                newData.forEach(row => {
                    row[header] = value
                });
            } else {
                newData[rowIndex] = {...newData[rowIndex], [header]: value};
            }
            return newData;
        });
    };

    // 4. 复制表格 (跳过第一列)
    const handleCopy = async () => {
        if (tableData.length === 0) return;
        const text = tableData
            .map(row => headers.slice(1).map(h => row[h]).join("\t"))
            .join("\n");

        try {
            await navigator.clipboard.writeText(text);
            setIsCopied(true);
            toast.success("已复制到剪贴板！", {position: "bottom-center"});
            setTimeout(() => setIsCopied(false), 1600);
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            toast.error(`复制失败：${message}`, {position: "bottom-center"});
        }
    }

    return (
        <div className="overflow-y-scroll min-h-screen p-2 bg-neutral-100 selection:bg-gray-300">
            {/* 底色层卡片 */}
            <div className="mx-auto max-w-6xl min-h-[calc(100vh-24px)] p-6 space-y-6 rounded-xl bg-white shadow-sm">
                {/* 头区 */}
                <div className="relative text-center">
                    {/* 标题 */}
                    <h1 className="text-3xl font-bold tracking-tight text-slate-900 mb-6">PDF 识别解析提取</h1>
                    {/* 付费模式开关 */}
                    <div className={cn("absolute right-0 top-0 flex gap-4 rounded-xl border px-4 py-3 duration-500",
                        isPaidMode
                            ? "border-orange-200 shadow-[0_0_20px_-3px_rgba(249,115,22,0.15)]"
                            : "border-slate-200 shadow-sm")}
                    >
                        <Label htmlFor="mode-toggle"
                               className={cn("text-sm font-medium duration-300", isPaidMode ? "text-slate-400" : "text-slate-900")}
                        >免费</Label>
                        <Switch
                            id="mode-toggle"
                            checked={isPaidMode}
                            onCheckedChange={setIsPaidMode}
                            className="data-[state=checked]:bg-orange-400 data-[state=unchecked]:bg-slate-200"
                        />
                        <Label htmlFor="mode-toggle"
                               className={cn("text-sm font-medium duration-300", isPaidMode ? "text-orange-600" : "text-slate-400")}
                        >付费</Label>
                    </div>
                </div>

                {/* 拖拽上传区 */}
                <div {...getRootProps()}    // 注入属性，把 div 变成 Dropzone
                    onMouseEnter={() => setIsHovered(true)}
                    onMouseLeave={() => setIsHovered(false)}
                    className={cn(
                        "flex cursor-pointer flex-col items-center gap-4 rounded-xl border-2 border-dashed p-10 text-center duration-200 text-sm font-semibold",
                        uiState.wrapperClass)}
                >
                    <input {...getInputProps()} />  {/* 注入属性，用 input 处理点击事件 */}
                    {uiState.icon}
                    {uiState.title}
                </div>

                {/* 数据提取后加载区 */}
                {tableData.length > 0 && (
                    <div className="animate-in slide-in-from-top-5 duration-500 space-y-4 ">
                        {/* 工具栏 */}
                        <div className="flex items-baseline justify-between border-b pb-4">
                            {/* 校验结果 */}
                            <div className="ml-16 translate-y-2 flex items-center gap-2.5 font-sans">
                                {/* 1. 图标圆点 */}
                                <div className="relative flex h-6 w-6 items-center justify-center">
                                    <AnimatePresence mode="popLayout">
                                        {validation.rowErrors === 0 && !validation.isTotalError ? (
                                            <motion.div
                                                key="success-dot"
                                                initial={{scale: 0}}
                                                animate={{scale: 1}}
                                                exit={{scale: 0}}
                                                transition={{type: "spring", stiffness: 700, damping: 30}}
                                                className="absolute inset-0 flex items-center justify-center rounded-full bg-emerald-100 text-emerald-600"
                                            >
                                                <Check animateOnView className="h-3.5 w-3.5 stroke-[3.5px]"/>
                                            </motion.div>
                                        ) : (
                                            <motion.div
                                                key="error-dot"
                                                initial={{scale: 0}}
                                                animate={{scale: 1}}
                                                exit={{scale: 0}}
                                                transition={{type: "spring", stiffness: 700, damping: 30}}
                                                className="absolute inset-0 flex items-center justify-center rounded-full bg-rose-100 text-rose-600"
                                            >
                                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                                                     strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"
                                                     className="h-3.5 w-3.5">
                                                    {/* ✗ 从中心点(12,12)向四个角发散绘制 */}
                                                    <motion.path d="M12 12 L6 6" initial={{pathLength: 0}}
                                                                 animate={{pathLength: 1}} transition={{
                                                        ease: "backOut",
                                                        duration: 0.5,
                                                        delay: 0.05
                                                    }}/>
                                                    <motion.path d="M12 12 L18 18" initial={{pathLength: 0}}
                                                                 animate={{pathLength: 1}} transition={{
                                                        ease: "backOut",
                                                        duration: 0.5,
                                                        delay: 0.05
                                                    }}/>
                                                    <motion.path d="M12 12 L6 18" initial={{pathLength: 0}}
                                                                 animate={{pathLength: 1}} transition={{
                                                        ease: "backOut",
                                                        duration: 0.5,
                                                        delay: 0.05
                                                    }}/>
                                                    <motion.path d="M12 12 L18 6" initial={{pathLength: 0}}
                                                                 animate={{pathLength: 1}} transition={{
                                                        ease: "backOut",
                                                        duration: 0.5,
                                                        delay: 0.05
                                                    }}/>
                                                </svg>
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </div>
                                {/* 2. 文字 Morph */}
                                <motion.div
                                    // layout
                                    animate={{
                                        color: validation.rowErrors === 0 && !validation.isTotalError
                                            ? "rgb(5, 150, 105)"  // emerald-600
                                            : "rgb(225, 29, 72)"  // rose-600
                                    }}
                                    transition={{color: {duration: 0.3}}}
                                    className="text-sm font-semibold tracking-tight"
                                >
                                    <TextMorph>
                                        {validation.rowErrors === 0 && !validation.isTotalError
                                            ? "校验无误"
                                            : `${[
                                                validation.rowErrors > 0 && `${validation.rowErrors} 行小计`,
                                                validation.isTotalError && "总价"
                                            ].filter(Boolean).join('、')} 校验有误`
                                        }
                                    </TextMorph>
                                </motion.div>
                            </div>
                            {/* 复制按钮 */}
                            <Button
                                onClick={handleCopy}
                                variant="outline"
                                className="shadow-md hover:border-slate-300 hover:shadow"
                            >
                                <Clipboard animate={isCopied}/>
                                复制表格内容 (无表头/无首列)
                            </Button>
                        </div>

                        {/* 数据表格 */}
                        <div className="overflow-x-auto rounded-xl shadow-sm border bg-white">
                            <table className="text-sm w-full border-hidden">
                                <thead className="bg-slate-100 text-xs">
                                <tr>
                                    {visibleHeaders.map((header) => (
                                        <th
                                            key={header}
                                            className={`text-slate-600 p-2 whitespace-nowrap ${
                                                header === "总价" && validation.isTotalError ? "text-red-600" : ""
                                            }`}
                                        >
                                            {header}
                                        </th>
                                    ))}
                                </tr>
                                </thead>
                                <tbody>
                                {validation.validatedData.map(({rowData, isRowError}, rowIndex) => (
                                    <tr key={rowIndex} className="hover:bg-slate-50">
                                        {visibleHeaders.map((header) => {
                                            // 校验逻辑
                                            const isCellError = (isRowError && ["数量", "单价", "小计"].includes(header))
                                                || (validation.isTotalError && header === "总价");

                                            return (
                                                <td
                                                    key={header}
                                                    onClick={(e) => e.currentTarget.querySelector('textarea')?.focus()}
                                                    className={cn("border cursor-text duration-300 focus-within:ring-2 focus-within:ring-inset",
                                                        isCellError ? "bg-red-100 focus-within:ring-red-400/80" : "focus-within:ring-blue-400/80")}
                                                >
                                                    <textarea
                                                        value={rowData[header] || ""}
                                                        onChange={(e) => updateCell(rowIndex, header, e.target.value)}
                                                        // 魔法：field-sizing-content 是 Tailwind v4 原生类，宽高随内容自动变化。Firefox 还没支持
                                                        className={cn("min-w-full field-sizing-content max-w-50 p-2 outline-none resize-none block",
                                                            ["品名", "备注", "地址"].includes(header) ? 'text-left' : 'text-center',
                                                            isCellError ? "text-red-700" : "")}
                                                        spellCheck={false}
                                                    />
                                                </td>
                                            );
                                        })}
                                    </tr>
                                ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}