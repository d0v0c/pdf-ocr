import { notFound } from 'next/navigation';
import Main from './Main';
import Demo from "./Demo";
export default async function Portal({ params }: {params: Promise<{ portal: string }>}) {
    const resolvedParams = await params;
    // 不放根目录，防止爬虫
    if (resolvedParams.portal === process.env.PORTAL_PATH) {
        return <Main />;
    }
    if (resolvedParams.portal === 'demo') {
        return <Demo />;
    }
    notFound();
}