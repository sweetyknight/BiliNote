import { useEffect, useRef } from 'react'
import { useTaskStore, ErrorInfo, ProgressDetails, TaskStatus, Transcript, AudioMeta } from '@/store/taskStore'
import { get_task_status } from '@/services/note.ts'
import toast from 'react-hot-toast'

// 状态消息映射
const STATUS_MESSAGES: Record<string, string> = {
  PENDING: '任务排队中，等待处理...',
  PARSING: '正在解析视频链接...',
  DOWNLOADING: '正在下载媒体文件...',
  TRANSCRIBING: '正在转写音频内容...',
  SUMMARIZING: '正在用 AI 生成笔记...',
  SAVING: '正在保存笔记...',
  SUCCESS: '笔记生成完成！',
  FAILED: '任务处理失败',
}

// 状态中文名称
const STATUS_NAMES: Record<string, string> = {
  PENDING: '排队等待',
  PARSING: '解析链接',
  DOWNLOADING: '下载媒体',
  TRANSCRIBING: '音频转写',
  SUMMARIZING: 'AI 生成笔记',
  SAVING: '保存结果',
}

// 根据错误信息生成可能的解决方案
const getSuggestions = (errorMessage: string, step?: string): string[] => {
  const suggestions: string[] = []
  const lowerMsg = errorMessage.toLowerCase()

  // 网络相关错误
  if (lowerMsg.includes('network') || lowerMsg.includes('timeout') || lowerMsg.includes('连接') || lowerMsg.includes('超时')) {
    suggestions.push('检查网络连接是否正常')
    suggestions.push('尝试刷新页面后重试')
  }

  // API Key 相关错误
  if (lowerMsg.includes('api') || lowerMsg.includes('key') || lowerMsg.includes('unauthorized') || lowerMsg.includes('401') || lowerMsg.includes('认证')) {
    suggestions.push('检查 API Key 是否正确配置')
    suggestions.push('确认 API Key 是否有足够的额度')
  }

  // 模型相关错误
  if (lowerMsg.includes('model') || lowerMsg.includes('模型')) {
    suggestions.push('检查所选模型是否可用')
    suggestions.push('尝试更换其他模型')
  }

  // 下载相关错误
  if (step === 'DOWNLOADING' || lowerMsg.includes('download') || lowerMsg.includes('下载')) {
    suggestions.push('检查视频链接是否有效')
    suggestions.push('确认视频是否有访问限制')
    suggestions.push('尝试更新 Cookie 配置')
  }

  // 转写相关错误
  if (step === 'TRANSCRIBING' || lowerMsg.includes('transcri') || lowerMsg.includes('转写') || lowerMsg.includes('whisper')) {
    suggestions.push('音频文件可能损坏，尝试重新下载')
    suggestions.push('检查转写服务是否正常运行')
  }

  // 文件相关错误
  if (lowerMsg.includes('file') || lowerMsg.includes('文件') || lowerMsg.includes('not found') || lowerMsg.includes('找不到')) {
    suggestions.push('检查文件路径是否正确')
    suggestions.push('确认服务器存储空间是否充足')
  }

  // 默认建议
  if (suggestions.length === 0) {
    suggestions.push('查看后端日志获取更多信息')
    suggestions.push('尝试重新生成笔记')
  }

  return suggestions
}

// 轮询失败后需要连续失败多少次才判定任务失败
const MAX_POLL_FAILURES = 5

export const useTaskPolling = (interval = 3000) => {
  const tasks = useTaskStore(state => state.tasks)
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)

  const tasksRef = useRef(tasks)
  // 记录每个任务的连续轮询失败次数
  const pollFailCountRef = useRef<Record<string, number>>({})

  // 每次 tasks 更新，把最新的 tasks 同步进去
  useEffect(() => {
    tasksRef.current = tasks
  }, [tasks])

  useEffect(() => {
    const timer = setInterval(async () => {
      const pendingTasks = tasksRef.current.filter(
        task => task.status != 'SUCCESS' && task.status != 'FAILED'
      )

      for (const task of pendingTasks) {
        try {
          const res = await get_task_status(task.id)
          const data = res as unknown as {
            status: TaskStatus
            message?: string
            details?: ProgressDetails
            updated_at?: string
            result?: { markdown: string; transcript: Transcript; audio_meta: AudioMeta }
            code?: string | number
          }
          const { status, message, details, updated_at } = data

          // 轮询成功，重置失败计数
          pollFailCountRef.current[task.id] = 0

          // 获取状态对应的默认消息，优先使用后端返回的消息
          const statusMessage = message || STATUS_MESSAGES[status] || '处理中...'
          const progressDetails: ProgressDetails | undefined = details

          if (status && status !== task.status) {
            if (status === 'SUCCESS') {
              const { markdown, transcript, audio_meta } = data.result!
              toast.success('笔记生成成功')
              updateTaskContent(task.id, {
                status,
                message: statusMessage,
                progressDetails: undefined,
                updatedAt: updated_at,
                errorInfo: undefined, // 清除错误信息
                markdown,
                transcript,
                audioMeta: audio_meta,
              })
            } else if (status === 'FAILED') {
              // 失败时收集详细错误信息
              const errorMessage = message || '任务处理失败，请查看后台日志'
              // 优先使用后端返回的失败步骤，回退到前端上次轮询的状态
              const failedStep = details?.failed_step || task.status
              const previousStep = failedStep as string

              const errorInfo: ErrorInfo = {
                message: errorMessage,
                code: data.code || 'UNKNOWN',
                step: STATUS_NAMES[previousStep] || previousStep,
                timestamp: updated_at || new Date().toLocaleString('zh-CN'),
                details: typeof data === 'object' ? JSON.stringify(data, null, 2) : undefined,
              }

              updateTaskContent(task.id, {
                status,
                message: errorMessage,
                progressDetails,
                updatedAt: updated_at,
                errorInfo
              })
              console.warn(`⚠️ 任务 ${task.id} 失败: ${errorMessage}`)
            } else {
              // 更新中间状态和消息
              updateTaskContent(task.id, {
                status,
                message: statusMessage,
                progressDetails,
                updatedAt: updated_at,
              })
            }
          } else if (message !== task.message || JSON.stringify(details) !== JSON.stringify(task.progressDetails)) {
            // 状态相同但消息或详情变化时也更新
            updateTaskContent(task.id, {
              message: statusMessage,
              progressDetails,
              updatedAt: updated_at,
            })
          }
        } catch (error: unknown) {
          // 增加失败计数
          const failCount = (pollFailCountRef.current[task.id] || 0) + 1
          pollFailCountRef.current[task.id] = failCount

          console.warn(`⚠️ 任务 ${task.id} 轮询失败 (${failCount}/${MAX_POLL_FAILURES})`, error)

          // 未达到最大失败次数，跳过本次，等待下一次轮询重试
          if (failCount < MAX_POLL_FAILURES) {
            continue
          }

          // 连续多次轮询失败，判定任务失败
          console.error(`❌ 任务 ${task.id} 连续 ${failCount} 次轮询失败，判定为失败`)
          const err = error as {
            msg?: string
            message?: string
            code?: string | number
            response?: { data?: { msg?: string; code?: string | number }; status?: number }
            stack?: string
          }
          const errorMessage =
            err?.msg ||
            err?.response?.data?.msg ||
            err?.message ||
            '网络请求失败，请稍后重试'
          const errorCode =
            err?.code ||
            err?.response?.data?.code ||
            err?.response?.status ||
            'NETWORK_ERROR'
          const previousStep = task.status

          const errorInfo: ErrorInfo = {
            message: errorMessage,
            code: errorCode,
            step: STATUS_NAMES[previousStep] || previousStep,
            timestamp: new Date().toLocaleString('zh-CN'),
            details:
              err?.stack ||
              (typeof error === 'object' ? JSON.stringify(error, null, 2) : String(error)),
          }

          updateTaskContent(task.id, {
            status: 'FAILED',
            message: errorMessage,
            errorInfo
          })
        }
      }
    }, interval)

    return () => clearInterval(timer)
  }, [interval, updateTaskContent])
}

export { getSuggestions, STATUS_NAMES }
