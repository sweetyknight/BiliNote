import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { Button } from '@/components/ui/button.tsx'
import { Copy, ArrowRight, Play, ExternalLink, AlertCircle, RefreshCw, ChevronDown, ChevronUp, Lightbulb, Clock, Hash, Layers } from 'lucide-react'
import { toast } from 'react-hot-toast'
import Error from '@/components/Lottie/error.tsx'
import Loading from '@/components/Lottie/Loading.tsx'
import Idle from '@/components/Lottie/Idle.tsx'
import StepBar from '@/pages/HomePage/components/StepBar.tsx'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { atomDark as codeStyle } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Zoom from 'react-medium-image-zoom'
import 'react-medium-image-zoom/dist/styles.css'
import gfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import 'github-markdown-css/github-markdown-light.css'
import { FC } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area.tsx'
import { useTaskStore } from '@/store/taskStore'
import { noteStyles } from '@/constant/note.ts'
import { MarkdownHeader } from '@/pages/HomePage/components/MarkdownHeader.tsx'
import TranscriptViewer from '@/pages/HomePage/components/transcriptViewer.tsx'
import MarkmapEditor from '@/pages/HomePage/components/MarkmapComponent.tsx'
import { exportToHtml } from '@/utils/exportHtml'
import { getSuggestions } from '@/hooks/useTaskPolling'

// 状态步骤对应的图标和颜色
const STATUS_CONFIG: Record<string, { icon: string; color: string; bgColor: string }> = {
  PENDING: { icon: '⏳', color: 'text-amber-600', bgColor: 'bg-amber-50' },
  PARSING: { icon: '🔗', color: 'text-emerald-600', bgColor: 'bg-emerald-50' },
  DOWNLOADING: { icon: '📥', color: 'text-cyan-600', bgColor: 'bg-cyan-50' },
  TRANSCRIBING: { icon: '🎤', color: 'text-violet-600', bgColor: 'bg-violet-50' },
  SUMMARIZING: { icon: '🤖', color: 'text-emerald-600', bgColor: 'bg-emerald-50' },
  SAVING: { icon: '💾', color: 'text-indigo-600', bgColor: 'bg-indigo-50' },
}

interface VersionNote {
  ver_id: string
  content: string
  style: string
  model_name: string
  created_at?: string
}

interface MarkdownViewerProps {
  content: string | VersionNote[]
  status: 'idle' | 'loading' | 'success' | 'failed'
}

const steps = [
  { label: '解析链接', key: 'PARSING' },
  { label: '下载音频', key: 'DOWNLOADING' },
  { label: '转写文字', key: 'TRANSCRIBING' },
  { label: '总结内容', key: 'SUMMARIZING' },
  { label: '保存完成', key: 'SUCCESS' },
]

const MarkdownViewer: FC<MarkdownViewerProps> = ({ status }) => {
  const [currentVerId, setCurrentVerId] = useState<string>('')
  const [selectedContent, setSelectedContent] = useState<string>('')
  const [modelName, setModelName] = useState<string>('')
  const [style, setStyle] = useState<string>('')
  const [createTime, setCreateTime] = useState<string>('')
  const [showErrorDetails, setShowErrorDetails] = useState(false)
  // 确保baseURL没有尾部斜杠
  const baseURL = (String(import.meta.env.VITE_API_BASE_URL || '').replace('/api','') || '').replace(/\/$/, '')
  const getCurrentTask = useTaskStore.getState().getCurrentTask
  const currentTask = useTaskStore(state => state.getCurrentTask())
  const taskStatus = currentTask?.status || 'PENDING'
  const retryTask = useTaskStore.getState().retryTask
  const isMultiVersion = Array.isArray(currentTask?.markdown)
  const [showTranscribe, setShowTranscribe] = useState(false)
  const [viewMode, setViewMode] = useState<'map' | 'preview'>('preview')
  // 多版本内容处理
  useEffect(() => {
    if (!currentTask) return

    if (!isMultiVersion) {
      setCurrentVerId('') // 清空旧版本 ID
      setModelName(currentTask.formData.model_name)
      setStyle(currentTask.formData.style)
      setCreateTime(currentTask.createdAt)
      setSelectedContent(currentTask?.markdown)
    } else {
      const latestVersion = [...currentTask.markdown].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )[0]

      if (latestVersion) {
        setCurrentVerId(latestVersion.ver_id)
      }
    }
  }, [currentTask, isMultiVersion, taskStatus])
  useEffect(() => {
    if (!currentTask || !isMultiVersion) return

    const currentVer = currentTask.markdown.find(v => v.ver_id === currentVerId)
    if (currentVer) {
      setModelName(currentVer.model_name)
      setStyle(currentVer.style)
      setCreateTime(currentVer.created_at || '')
      setSelectedContent(currentVer.content)
    }
  }, [currentTask, currentVerId, isMultiVersion])
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(selectedContent)
      toast.success('已复制到剪贴板')
    } catch {
      toast.error('复制失败')
    }
  }
  const handleDownload = () => {
    const task = getCurrentTask()
    const name = task?.audioMeta.title || 'note'
    const blob = new Blob([selectedContent], { type: 'text/markdown;charset=utf-8' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${name}.md`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const handleDownloadHtml = async () => {
    const task = getCurrentTask()
    const name = task?.audioMeta.title || 'note'
    try {
      await exportToHtml(selectedContent, name, baseURL)
      toast.success('HTML 导出成功')
    } catch (error) {
      console.error('导出 HTML 失败:', error)
      toast.error('HTML 导出失败')
    }
  }

  if (status === 'loading') {
    const statusConfig = STATUS_CONFIG[taskStatus] || STATUS_CONFIG.PENDING
    const progressMessage = currentTask?.message || '正在处理中...'
    const progressDetails = currentTask?.progressDetails
    const updatedAt = currentTask?.updatedAt
    
    // 格式化详情显示的标签
    const detailLabels: Record<string, string> = {
      video_url: '视频链接',
      platform: '平台',
      model: '模型',
      quality: '质量',
      need_video: '需要视频',
      sub_step: '子步骤',
      video_file: '视频文件',
      video_size: '视频大小',
      audio_file: '音频文件',
      audio_size: '音频大小',
      title: '标题',
      duration: '时长',
      transcriber: '转写器',
      language: '语言',
      segments_count: '片段数',
      text_length: '文本长度',
      style: '风格',
      has_images: '包含图片',
      markdown_length: '笔记长度',
    }
    
    return (
      <div className="flex h-full w-full flex-col items-center justify-center space-y-6 overflow-auto px-8 py-8 text-neutral-500">
        {/* 步骤条 */}
        <div className="w-full max-w-2xl">
          <StepBar steps={steps} currentStep={taskStatus} />
        </div>
        
        {/* 动画加载 */}
        <Loading className="h-5 w-5" />
        
        {/* 进度信息卡片 */}
        <div className={`w-full max-w-lg rounded-xl border ${statusConfig.bgColor} p-6 shadow-sm transition-all duration-300`}>
          <div className="flex items-center gap-3">
            <span className="text-2xl">{statusConfig.icon}</span>
            <div className="flex-1">
              <p className={`text-base font-semibold ${statusConfig.color}`}>
                {progressMessage}
              </p>
              {updatedAt && (
                <p className="mt-1 text-xs text-neutral-400">
                  更新于 {updatedAt}
                </p>
              )}
            </div>
          </div>
          
          {/* 进度动画条 */}
          <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-neutral-200">
            <div 
              className={`h-full rounded-full ${statusConfig.color.replace('text-', 'bg-')} animate-pulse`}
              style={{ 
                width: taskStatus === 'PENDING' ? '10%' : 
                       taskStatus === 'PARSING' ? '25%' :
                       taskStatus === 'DOWNLOADING' ? '40%' :
                       taskStatus === 'TRANSCRIBING' ? '60%' :
                       taskStatus === 'SUMMARIZING' ? '80%' :
                       taskStatus === 'SAVING' ? '95%' : '50%',
                transition: 'width 0.5s ease-in-out'
              }}
            />
          </div>
          
          {/* 详细信息区域 */}
          {progressDetails && Object.keys(progressDetails).length > 0 && (
            <div className="mt-4 rounded-lg bg-white/60 p-4">
              <p className="mb-2 text-xs font-semibold text-neutral-500 flex items-center gap-1">
                <Layers className="h-3 w-3" />
                处理详情
              </p>
              <div className="space-y-1.5 text-xs">
                {Object.entries(progressDetails).map(([key, value]) => {
                  // 跳过一些不需要显示的字段
                  if (key === 'sub_step' || value === undefined || value === '') return null
                  
                  const label = detailLabels[key] || key
                  let displayValue = String(value)
                  
                  // 特殊处理布尔值
                  if (typeof value === 'boolean') {
                    displayValue = value ? '是' : '否'
                  }
                  
                  // 特殊处理长文本（如URL）
                  if (key === 'video_url' && displayValue.length > 50) {
                    displayValue = displayValue.slice(0, 50) + '...'
                  }
                  
                  return (
                    <div key={key} className="flex items-center gap-2">
                      <span className="text-neutral-400 min-w-[60px]">{label}:</span>
                      <span className={`font-medium ${statusConfig.color} truncate`} title={String(value)}>
                        {displayValue}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
        
        <p className="text-xs text-neutral-400">
          💡 小提示：处理过程中请勿关闭页面
        </p>
      </div>
    )
  }

  if (status === 'idle') {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center space-y-3 text-neutral-500">
        <Idle />
        <div className="text-center">
          <p className="text-lg font-bold">输入视频链接并点击“生成笔记”</p>
          <p className="mt-2 text-xs text-neutral-500">支持哔哩哔哩、YouTube 、抖音等视频平台</p>
        </div>
      </div>
    )
  }

  if (status === 'failed' && !isMultiVersion) {
    const errorInfo = currentTask?.errorInfo
    const errorMessage = errorInfo?.message || currentTask?.message || '未知错误，请查看后台日志'
    const suggestions = getSuggestions(errorMessage, currentTask?.status)
    
    // 生成完整的错误报告用于复制
    const generateErrorReport = () => {
      const report = [
        '=== BiliNote 错误报告 ===',
        `时间: ${errorInfo?.timestamp || new Date().toLocaleString('zh-CN')}`,
        `任务ID: ${currentTask?.id || '未知'}`,
        `失败步骤: ${errorInfo?.step || '未知'}`,
        `错误代码: ${errorInfo?.code || '未知'}`,
        `视频链接: ${currentTask?.formData?.video_url || '未知'}`,
        `平台: ${currentTask?.formData?.platform || '未知'}`,
        `模型: ${currentTask?.formData?.model_name || '未知'}`,
        '',
        '--- 错误信息 ---',
        errorMessage,
        '',
        '--- 详细信息 ---',
        errorInfo?.details || '无',
      ].join('\n')
      return report
    }
    
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-4 overflow-auto px-4 py-8">
        <Error />
        
        {/* 错误信息卡片 */}
        <div className="w-full max-w-2xl rounded-xl border border-red-100 bg-gradient-to-br from-red-50 to-orange-50 p-6 shadow-lg">
          {/* 标题区域 */}
          <div className="flex items-start gap-3">
            <div className="rounded-full bg-red-100 p-2">
              <AlertCircle className="h-5 w-5 text-red-500" />
            </div>
            <div className="flex-1">
              <p className="text-lg font-bold text-red-600">笔记生成失败</p>
              <p className="mt-1 text-sm text-red-500/80">
                {errorMessage}
              </p>
            </div>
          </div>
          
          {/* 错误摘要信息 */}
          <div className="mt-4 grid grid-cols-2 gap-3 rounded-lg bg-white/60 p-4 text-sm">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-neutral-400" />
              <span className="text-neutral-500">发生时间:</span>
              <span className="font-medium text-neutral-700">{errorInfo?.timestamp || '-'}</span>
            </div>
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-neutral-400" />
              <span className="text-neutral-500">失败步骤:</span>
              <span className="font-medium text-red-600">{errorInfo?.step || '未知'}</span>
            </div>
            <div className="flex items-center gap-2">
              <Hash className="h-4 w-4 text-neutral-400" />
              <span className="text-neutral-500">错误代码:</span>
              <span className="font-mono text-xs font-medium text-neutral-700">{errorInfo?.code || '-'}</span>
            </div>
            <div className="flex items-center gap-2">
              <Hash className="h-4 w-4 text-neutral-400" />
              <span className="text-neutral-500">任务ID:</span>
              <span className="font-mono text-xs text-neutral-500 truncate" title={currentTask?.id}>{currentTask?.id?.slice(0, 8) || '-'}...</span>
            </div>
          </div>
          
          {/* 可能的解决方案 */}
          <div className="mt-4 rounded-lg bg-amber-50 border border-amber-100 p-4">
            <div className="flex items-center gap-2 text-amber-700 font-medium mb-2">
              <Lightbulb className="h-4 w-4" />
              <span>可能的解决方案</span>
            </div>
            <ul className="space-y-1.5 text-sm text-amber-600">
              {suggestions.map((suggestion, index) => (
                <li key={index} className="flex items-start gap-2">
                  <span className="text-amber-400 mt-0.5">•</span>
                  <span>{suggestion}</span>
                </li>
              ))}
            </ul>
          </div>
          
          {/* 展开详细错误信息 */}
          <div className="mt-4">
            <button
              onClick={() => setShowErrorDetails(!showErrorDetails)}
              className="flex w-full items-center justify-between rounded-lg bg-red-100/50 px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-100 transition-colors"
            >
              <span className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4" />
                {showErrorDetails ? '收起详细信息' : '展开详细信息'}
              </span>
              {showErrorDetails ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
            
            {showErrorDetails && (
              <div className="mt-3 space-y-3">
                {/* 请求信息 */}
                <div className="rounded-lg bg-neutral-50 p-4">
                  <p className="text-xs font-semibold text-neutral-500 mb-2">请求信息</p>
                  <div className="space-y-1 text-xs text-neutral-600">
                    <p><span className="text-neutral-400">视频链接:</span> {currentTask?.formData?.video_url || '-'}</p>
                    <p><span className="text-neutral-400">平台:</span> {currentTask?.formData?.platform || '-'}</p>
                    <p><span className="text-neutral-400">模型:</span> {currentTask?.formData?.model_name || '-'}</p>
                    <p><span className="text-neutral-400">质量:</span> {currentTask?.formData?.quality || '-'}</p>
                  </div>
                </div>
                
                {/* 原始错误信息 */}
                <div className="rounded-lg bg-red-100/30 p-4">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-semibold text-red-500">原始错误信息</p>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(generateErrorReport())
                        toast.success('完整错误报告已复制')
                      }}
                      className="flex items-center gap-1 rounded px-2 py-1 text-xs text-red-400 hover:bg-red-100 hover:text-red-600 transition-colors"
                      title="复制完整错误报告"
                    >
                      <Copy className="h-3 w-3" />
                      复制报告
                    </button>
                  </div>
                  <ScrollArea className="max-h-40">
                    <code className="block whitespace-pre-wrap break-all text-xs text-red-700 font-mono leading-relaxed">
                      {errorInfo?.details || errorMessage}
                    </code>
                  </ScrollArea>
                </div>
              </div>
            )}
          </div>
          
          {/* 操作按钮 */}
          <div className="mt-5 flex gap-3">
            <Button 
              onClick={() => {
                setShowErrorDetails(false)
                retryTask(currentTask.id)
              }} 
              className="flex-1 bg-gradient-to-r from-red-500 to-orange-500 hover:from-red-600 hover:to-orange-600 shadow-md"
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              重新生成
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                navigator.clipboard.writeText(generateErrorReport())
                toast.success('错误报告已复制，可粘贴到 Issue 中反馈')
              }}
              className="border-red-200 text-red-600 hover:bg-red-50"
            >
              <Copy className="mr-2 h-4 w-4" />
              复制报告
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      <MarkdownHeader
        currentTask={currentTask}
        isMultiVersion={isMultiVersion}
        currentVerId={currentVerId}
        setCurrentVerId={setCurrentVerId}
        modelName={modelName}
        style={style}
        noteStyles={noteStyles}
        onCopy={handleCopy}
        onDownload={handleDownload}
        onDownloadHtml={handleDownloadHtml}
        createAt={createTime}
        showTranscribe={showTranscribe}
        setShowTranscribe={setShowTranscribe}
        viewMode={viewMode}
        setViewMode={setViewMode}
      />

      {viewMode === 'map' ? (
        <div className="flex w-full flex-1 overflow-hidden bg-white">
          <div className={'w-full'}>
            <MarkmapEditor
              value={selectedContent}
              height="100%" // 根据需求可以设定百分比或固定高度
              title={currentTask?.audioMeta?.title || '思维导图'}
            />
          </div>
        </div>
      ) : (
        <div className="flex min-w-0 flex-1 overflow-hidden bg-white py-2">
          {selectedContent && selectedContent !== 'loading' && selectedContent !== 'empty' ? (
            <>
              <ScrollArea className="min-w-0 flex-1 overflow-x-hidden">
                <div className={'markdown-body min-w-0 max-w-full overflow-hidden break-words px-4'} style={{ wordBreak: 'break-word', overflowWrap: 'break-word' }}>
                  <ReactMarkdown
                    remarkPlugins={[gfm, remarkMath]}
                    rehypePlugins={[rehypeKatex]}
                    components={{
                      // Headings with improved styling and anchor links
                      h1: ({ children, ...props }) => (
                        <h1
                          className="text-primary my-6 scroll-m-20 text-3xl font-extrabold tracking-tight lg:text-4xl"
                          {...props}
                        >
                          {children}
                        </h1>
                      ),
                      h2: ({ children, ...props }) => (
                        <h2
                          className="text-primary mt-10 mb-4 scroll-m-20 border-b pb-2 text-2xl font-semibold tracking-tight first:mt-0"
                          {...props}
                        >
                          {children}
                        </h2>
                      ),
                      h3: ({ children, ...props }) => (
                        <h3
                          className="text-primary mt-8 mb-4 scroll-m-20 text-xl font-semibold tracking-tight"
                          {...props}
                        >
                          {children}
                        </h3>
                      ),
                      h4: ({ children, ...props }) => (
                        <h4
                          className="text-primary mt-6 mb-2 scroll-m-20 text-lg font-semibold tracking-tight"
                          {...props}
                        >
                          {children}
                        </h4>
                      ),

                      // Paragraphs with better line height
                      p: ({ children, ...props }) => (
                        <p className="leading-7 [&:not(:first-child)]:mt-6" {...props}>
                          {children}
                        </p>
                      ),

                      // Enhanced links with special handling for "原片" links
                      a: ({ href, children, ...props }) => {
                        const isOriginLink =
                          typeof children[0] === 'string' &&
                          (children[0] as string).startsWith('原片 @')

                        if (isOriginLink) {
                          const timeMatch = (children[0] as string).match(/原片 @ (\d{2}:\d{2})/)
                          const timeText = timeMatch ? timeMatch[1] : '原片'

                          return (
                            <span className="origin-link my-2 inline-flex">
                              <a
                                href={href}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-700 transition-colors hover:bg-emerald-100"
                                {...props}
                              >
                                <Play className="h-3.5 w-3.5" />
                                <span>原片（{timeText}）</span>
                              </a>
                            </span>
                          )
                        }

                        // Default link styling with external indicator
                        return (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary hover:text-primary/80 inline-flex items-center gap-0.5 font-medium underline underline-offset-4"
                            {...props}
                          >
                            {children}
                            {href?.startsWith('http') && (
                              <ExternalLink className="ml-0.5 inline-block h-3 w-3" />
                            )}
                          </a>
                        )
                      },

                      // Enhanced image with zoom capability
                      img: ({ ...props }) =>{
                        // Fix the URL by removing the 'undefined' prefix if it exists
                        let src = props.src
                        if (src.startsWith('/')) {
                          src = baseURL + src
                        }
                        props.src = src

                     return(
                      <div className="my-8 flex justify-center">
                          <Zoom>
                            <img
                              {...props}
                              className="max-w-full cursor-zoom-in rounded-lg object-cover shadow-md transition-all hover:shadow-lg"
                              style={{ maxHeight: '500px' }}
                            />
                          </Zoom>
                        </div>
                      )},

                      // Better strong/bold text
                      strong: ({ children, ...props }) => (
                        <strong className="text-primary font-bold" {...props}>
                          {children}
                        </strong>
                      ),

                      // Enhanced list items with support for "fake headings"
                      li: ({ children, ...props }) => {
                        const rawText = String(children)
                        const isFakeHeading = /^(\*\*.+\*\*)$/.test(rawText.trim())

                        if (isFakeHeading) {
                          return (
                            <div className="text-primary my-4 text-lg font-bold">{children}</div>
                          )
                        }

                        return (
                          <li className="my-1" {...props}>
                            {children}
                          </li>
                        )
                      },

                      // Enhanced unordered lists
                      ul: ({ children, ...props }) => (
                        <ul className="my-6 ml-6 list-disc [&>li]:mt-2" {...props}>
                          {children}
                        </ul>
                      ),

                      // Enhanced ordered lists
                      ol: ({ children, ...props }) => (
                        <ol className="my-6 ml-6 list-decimal [&>li]:mt-2" {...props}>
                          {children}
                        </ol>
                      ),

                      // Enhanced blockquotes
                      blockquote: ({ children, ...props }) => (
                        <blockquote
                          className="border-primary/20 text-muted-foreground mt-6 border-l-4 pl-4 italic"
                          {...props}
                        >
                          {children}
                        </blockquote>
                      ),

                      // Enhanced code blocks with syntax highlighting and copy button
                                      code: ({ inline, className, children, ...props }) => {
                                        const match = /language-(\w+)/.exec(className || '')
                                        const codeContent = String(children).replace(/\n$/, '')

                                        if (!inline && match) {
                                          return (
                                            <div className="group bg-muted relative my-6 max-w-full overflow-hidden rounded-lg border shadow-sm">
                                              <div className="bg-muted text-muted-foreground flex items-center justify-between px-4 py-1.5 text-sm font-medium">
                                                <div>{match[1].toUpperCase()}</div>
                                                <button
                                                  onClick={() => {
                                                    navigator.clipboard.writeText(codeContent)
                                                    toast.success('代码已复制')
                                                  }}
                                                  className="bg-background/80 hover:bg-background flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors"
                                                >
                                                  <Copy className="h-3.5 w-3.5" />
                                                  复制
                                                </button>
                                              </div>
                                              <div className="overflow-x-auto">
                                                <SyntaxHighlighter
                                                  style={codeStyle}
                                                  language={match[1]}
                                                  PreTag="div"
                                                  className="!bg-muted !m-0 !p-0"
                                                  customStyle={{
                                                    margin: 0,
                                                    padding: '1rem',
                                                    background: 'transparent',
                                                    fontSize: '0.9rem',
                                                  }}
                                                  {...props}
                                                >
                                                  {codeContent}
                                                </SyntaxHighlighter>
                                              </div>
                                            </div>
                                          )
                                        }

                                        // Inline code styling
                                        return (
                                          <code
                                            className="bg-muted relative rounded px-[0.3rem] py-[0.2rem] font-mono text-sm break-all"
                                            {...props}
                                          >
                                            {children}
                                          </code>
                                        )
                                      },

                      // Enhanced tables
                                      table: ({ children, ...props }) => (
                                        <div className="my-6 w-full overflow-x-auto">
                                          <table className="min-w-full border-collapse text-sm" {...props}>
                                            {children}
                                          </table>
                                        </div>
                                      ),

                      // Table headers
                      th: ({ children, ...props }) => (
                        <th
                          className="border-muted-foreground/20 border px-4 py-2 text-left font-medium [&[align=center]]:text-center [&[align=right]]:text-right"
                          {...props}
                        >
                          {children}
                        </th>
                      ),

                      // Table cells
                      td: ({ children, ...props }) => (
                        <td
                          className="border-muted-foreground/20 border px-4 py-2 text-left [&[align=center]]:text-center [&[align=right]]:text-right"
                          {...props}
                        >
                          {children}
                        </td>
                      ),

                      // Horizontal rule
                      hr: ({ ...props }) => (
                        <hr className="border-muted-foreground/20 my-8" {...props} />
                      ),
                    }}
                  >
                    {selectedContent}
                  </ReactMarkdown>
                </div>
              </ScrollArea>
              {showTranscribe && (
                <div className={'ml-2 w-2/4'}>
                  <TranscriptViewer />
                </div>
              )}
            </>
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <div className="w-[300px] flex-col justify-items-center">
                <div className="bg-primary-light mb-4 flex h-16 w-16 items-center justify-center rounded-full">
                  <ArrowRight className="text-primary h-8 w-8" />
                </div>
                <p className="mb-2 text-neutral-600">输入视频链接并点击"生成笔记"按钮</p>
                <p className="text-xs text-neutral-500">支持哔哩哔哩、YouTube等视频网站</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default MarkdownViewer
