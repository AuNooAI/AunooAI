import { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import html2canvas from 'html2canvas';

interface ChartDownloadButtonProps {
  targetId: string;
  filename?: string;
}

export function ChartDownloadButton({ targetId, filename }: ChartDownloadButtonProps) {
  const [busy, setBusy] = useState(false);

  const handleDownload = async () => {
    const el = document.getElementById(targetId);
    if (!el) return;
    setBusy(true);
    try {
      const canvas = await html2canvas(el, {
        backgroundColor: '#ffffff',
        scale: 2,
        logging: false,
        useCORS: true,
      });
      const link = document.createElement('a');
      link.download = `${filename || targetId}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
    } catch (err) {
      console.error('Chart download failed:', err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      onClick={handleDownload}
      disabled={busy}
      title="Download chart as PNG"
      className="p-1 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
    >
      {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
    </button>
  );
}
