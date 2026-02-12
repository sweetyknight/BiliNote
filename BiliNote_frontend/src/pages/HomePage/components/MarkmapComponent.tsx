import { useEffect, useRef, useState } from 'react'
import { Markmap } from 'markmap-view'
import { transformer } from '@/lib/markmap.ts'
import { Toolbar } from 'markmap-toolbar'
import 'markmap-toolbar/dist/style.css'

type ToolbarItem = Parameters<Toolbar['register']>[0]

export interface MarkmapEditorProps {
  /** 要渲染的 Markdown 文本 */
  value: string
  /** Toolbar 上要展示的 item id 列表，默认使用 Toolbar.defaultItems */
  toolbarItems?: string[]
  /** 自定义按钮列表，会依次注册 */
  customButtons?: ToolbarItem[]
  /** 容器 SVG 的高度，默认为 600px */
  height?: string
  /** 文档标题，用于导出HTML时的文件名 */
  title?: string
}

export default function MarkmapEditor({
  value,
  toolbarItems,
  customButtons = [],
  height = '600px',
  title = 'mindmap',
}: MarkmapEditorProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const mmRef = useRef<Markmap | undefined>()
  const toolbarRef = useRef<HTMLDivElement>(null)

  // 用于跟踪是否处于全屏状态
  const [isFullscreen, setIsFullscreen] = useState(false)

  // 监听全屏状态变化
  useEffect(() => {
    const handler = () => {
      setIsFullscreen(!!document.fullscreenElement)
    }
    document.addEventListener('fullscreenchange', handler)
    return () => {
      document.removeEventListener('fullscreenchange', handler)
    }
  }, [])

  // 进入全屏
  const enterFullscreen = () => {
    const el = svgRef.current?.parentElement
    if (el && el.requestFullscreen) {
      el.requestFullscreen()
    }
  }

  // 退出全屏
  const exitFullscreen = () => {
    if (document.exitFullscreen) {
      document.exitFullscreen()
    }
  }
  
  // 导出HTML思维导图
  const exportHtml = () => {
    try {
      const { root } = transformer.transform(value)
      const data = JSON.stringify(root)
      
      // 创建HTML内容
      const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title || 'BiliNote思维导图'}</title>
  <style>
  body {
    margin: 0;
    padding: 0;
    font-family: sans-serif;
  }
  #mindmap {
    display: block;
    width: 100%;
    height: 100vh;
  }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
  <script src="https://cdn.jsdelivr.net/npm/markmap-view@0.18.10"></script>
</head>
<body>
  <svg id="mindmap"></svg>
  <script>
  (async () => {
    const { markmap } = window;
    const { Markmap } = markmap;
    const mm = Markmap.create(document.getElementById('mindmap'));
    mm.setData(${data});
    mm.fit();
  })();
  </script>
</body>
</html>`;
      
      const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${title || 'mindmap'}.html`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('导出HTML失败:', error);
    }
  };

  // 导出PNG思维导图
  const exportPng = () => {
    try {
      if (!svgRef.current) return;
      
      const svgEl = svgRef.current;
      
      // 获取SVG实际尺寸
      const svgWidth = svgEl.width.baseVal.value || svgEl.clientWidth || 800;
      const svgHeight = svgEl.height.baseVal.value || svgEl.clientHeight || 600;
      
      // 设置足够大的缩放比例以确保高清输出
      const scale = 3;
      
      // 克隆SVG以避免修改原始SVG
      const clonedSvg = svgEl.cloneNode(true) as SVGSVGElement;
      
      // 设置SVG的背景为白色
      const style = document.createElementNS('http://www.w3.org/2000/svg', 'style');
      style.textContent = 'svg { background-color: white; }';
      clonedSvg.insertBefore(style, clonedSvg.firstChild);
      
      // 确保SVG有正确的命名空间
      clonedSvg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      clonedSvg.setAttribute('width', svgWidth.toString());
      clonedSvg.setAttribute('height', svgHeight.toString());
      
      // 将SVG转换为Data URI (避免使用Blob URL来解决跨域问题)
      const svgData = new XMLSerializer().serializeToString(clonedSvg);
      const svgBase64 = btoa(unescape(encodeURIComponent(svgData)));
      const dataUri = `data:image/svg+xml;base64,${svgBase64}`;
      
      // 创建Canvas
      const canvas = document.createElement('canvas');
      canvas.width = svgWidth * scale;
      canvas.height = svgHeight * scale;
      
      // 获取上下文并设置白色背景
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        throw new Error('无法获取Canvas上下文');
      }
      
      // 设置白色背景
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      
      // 创建Image对象
      const img = new Image();
      
      // 当图片加载完成后，在Canvas上绘制并导出
      img.onload = () => {
        try {
          // 应用缩放
          ctx.setTransform(scale, 0, 0, scale, 0, 0);
          
          // 绘制SVG
          ctx.drawImage(img, 0, 0);
          
          // 重置变换
          ctx.setTransform(1, 0, 0, 1, 0, 0);
          
          // 将Canvas转换为PNG Blob
          canvas.toBlob((blob) => {
            if (blob) {
              // 创建下载链接
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `${title || 'mindmap'}.png`;
              document.body.appendChild(a);
              a.click();
              document.body.removeChild(a);
              URL.revokeObjectURL(url);
            } else {
              console.error('无法创建Blob对象');
            }
          }, 'image/png');
        } catch (err) {
          console.error('Canvas处理失败:', err);
        }
      };
      
      // 设置图片加载错误处理
      img.onerror = (error) => {
        console.error('导出PNG失败（图片加载错误）:', error);
      };
      
      // 开始加载SVG图像 (使用Data URI而不是Blob URL)
      img.src = dataUri;
      
    } catch (error) {
      console.error('导出PNG失败:', error);
    }
  };

  // 初始化 Markmap 实例 + Toolbar
  useEffect(() => {
    if (!svgRef.current || mmRef.current) return
    const mm = Markmap.create(svgRef.current)
    mmRef.current = mm

    if (toolbarRef.current) {
      toolbarRef.current.innerHTML = ''
      const toolbar = new Toolbar()
      toolbar.attach(mm)
      customButtons.forEach(btn => toolbar.register(btn))
      toolbar.setItems(toolbarItems ?? Toolbar.defaultItems)
      toolbarRef.current.appendChild(toolbar.render())
    }
  }, [customButtons, toolbarItems])

  // 当 value 变化时，重新渲染数据
  useEffect(() => {
    const mm = mmRef.current
    if (!mm) return
    const { root } = transformer.transform(value)
    mm.setData(root).then(() => mm.fit())
  }, [value])

  // 文本输入变化回调（如果你自行添加 textarea 编辑区）
  // const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
  //   onChange(e.target.value)
  // }

  return (
    <div className="relative flex h-full flex-col bg-white">
      {/* 全屏/退出全屏 按钮 */}
      <div className="absolute top-2 right-2 z-20 flex space-x-2">
        <button
          onClick={exportPng}
          className="rounded p-1 hover:bg-gray-200"
          title="导出PNG思维导图"
        >
          🖼️
        </button>
        <button
          onClick={exportHtml}
          className="rounded p-1 hover:bg-gray-200"
          title="导出HTML思维导图"
        >
          💾
        </button>
        {isFullscreen ? (
          <button
            onClick={exitFullscreen}
            className="rounded p-1 hover:bg-gray-200"
            title="退出全屏"
          >
            🗗
          </button>
        ) : (
          <button onClick={enterFullscreen} className="rounded p-1 hover:bg-gray-200" title="全屏">
            🗖
          </button>
        )}
      </div>

      {/* 如果需要编辑区，就自己加一个 <textarea> 并把 handleChange 绑上 */}
      {/* <textarea value={value} onChange={handleChange} className="mb-2 p-2 border rounded" /> */}

      {/* 思维导图区 */}
      <svg ref={svgRef} className="w-full flex-1" style={{ height, overflow: 'auto' }} />

      {/* 如果你还想保留 markmap-toolbar */}
      {/* <div ref={toolbarRef} className="absolute right-2 bottom-2 z-10" /> */}
    </div>
  )
}
