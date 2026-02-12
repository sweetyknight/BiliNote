import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { delete_task, generateNote, get_note_history } from '@/services/note.ts'
import { v4 as uuidv4 } from 'uuid'
import toast from 'react-hot-toast'


export type TaskStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'PARSING' | 'DOWNLOADING' | 'TRANSCRIBING' | 'SUMMARIZING' | 'SAVING'

export interface AudioMeta {
  cover_url: string
  duration: number
  file_path: string
  platform: string
  raw_info: unknown
  title: string
  video_id: string
}

export interface Segment {
  start: number
  end: number
  text: string
}

export interface Transcript {
  full_text: string
  language: string
  raw: unknown
  segments: Segment[]
}
export interface Markdown {
  ver_id: string
  content: string
  style: string
  model_name: string
  created_at: string
}

export interface ErrorInfo {
  message: string        // 错误消息
  code?: number | string // 错误代码
  step?: string          // 失败的步骤
  timestamp?: string     // 错误发生时间
  details?: string       // 详细堆栈或额外信息
}

// 进度详情
export interface ProgressDetails {
  [key: string]: string | number | boolean | undefined
}

export interface Task {
  id: string
  markdown: string|Markdown [] //为了兼容之前的笔记
  transcript: Transcript
  status: TaskStatus
  message?: string // 进度消息
  progressDetails?: ProgressDetails // 进度详情（文件大小、时长等）
  updatedAt?: string // 最后更新时间
  errorInfo?: ErrorInfo // 详细错误信息
  audioMeta: AudioMeta
  createdAt: string
  formData: TaskFormData
}

export interface TaskFormData {
  video_url: string
  link?: boolean
  screenshot?: boolean
  platform: string
  quality: string
  model_name: string
  provider_id: string
  format?: string[]
  style?: string
  extras?: string
  video_understanding?: boolean
  video_interval?: number
  grid_size?: number[]
}

interface HistoryNote {
  id: string
  status?: TaskStatus
  markdown?: string | Markdown[]
  transcript?: Partial<Transcript>
  audioMeta?: Partial<AudioMeta>
  createdAt?: string
  platform?: string
  formData?: Partial<TaskFormData>
}

interface TaskStore {
  tasks: Task[]
  currentTaskId: string | null
  isLoadingHistory: boolean
  addPendingTask: (taskId: string, platform: string, formData?: TaskFormData) => void
  updateTaskContent: (id: string, data: Partial<Omit<Task, 'id' | 'createdAt'>>) => void
  removeTask: (id: string) => void
  clearTasks: () => void
  setCurrentTask: (taskId: string | null) => void
  getCurrentTask: () => Task | null
  retryTask: (id: string, payload?: TaskFormData) => void
  loadHistoryNotes: () => Promise<void>
}

export const useTaskStore = create<TaskStore>()(
  persist(
    (set, get) => ({
      tasks: [],
      currentTaskId: null,
      isLoadingHistory: false,

      // 从服务器加载历史笔记
      loadHistoryNotes: async () => {
        // 避免重复加载
        if (get().isLoadingHistory) return
        
        set({ isLoadingHistory: true })
        
        try {
          const historyNotes = (await get_note_history()) as HistoryNote[]
          
          if (!historyNotes || historyNotes.length === 0) {
            set({ isLoadingHistory: false })
            return
          }
          
          // 获取当前本地任务的 ID 列表
          const existingIds = new Set(get().tasks.map(t => t.id))
          
          // 过滤出本地不存在的笔记
          const newNotes = historyNotes
            .filter(note => !existingIds.has(note.id))
            .map(note => ({
              id: note.id,
              status: note.status || 'SUCCESS',
              markdown: note.markdown || '',
              transcript: note.transcript || {
                full_text: '',
                language: '',
                raw: null,
                segments: [],
              },
              audioMeta: note.audioMeta || {
                cover_url: '',
                duration: 0,
                file_path: '',
                platform: note.platform || 'local',
                raw_info: null,
                title: note.audioMeta?.title || '未命名笔记',
                video_id: note.audioMeta?.video_id || note.id,
              },
              createdAt: note.createdAt || new Date().toISOString(),
              platform: note.platform || 'local',
              formData: note.formData || {
                video_url: note.audioMeta?.file_path || '',
                platform: note.platform || 'local',
                quality: 'fast',
                model_name: '',
                provider_id: '',
              },
            }))
          
          if (newNotes.length > 0) {
            set(state => ({
              tasks: [...state.tasks, ...newNotes],
              isLoadingHistory: false,
            }))
            console.log(`✅ 从服务器加载了 ${newNotes.length} 条历史笔记`)
          } else {
            set({ isLoadingHistory: false })
          }
        } catch (e) {
          console.error('❌ 加载历史笔记失败:', e)
          set({ isLoadingHistory: false })
        }
      },

      addPendingTask: (taskId: string, platform: string, formData?: TaskFormData) =>

        set(state => ({
          tasks: [
            {
              formData: formData || {
                video_url: '',
                link: false,
                screenshot: false,
                platform,
                quality: 'fast',
                model_name: '',
                provider_id: '',
                format: [],
              },
              id: taskId,
              status: 'PENDING',
              message: '任务已提交，等待处理...',
              markdown: '',
              platform: platform,
              transcript: {
                full_text: '',
                language: '',
                raw: null,
                segments: [],
              },
              createdAt: new Date().toISOString(),
              audioMeta: {
                cover_url: '',
                duration: 0,
                file_path: '',
                platform: '',
                raw_info: null,
                title: '',
                video_id: '',
              },
            },
            ...state.tasks,
          ],
          currentTaskId: taskId, // 默认设置为当前任务
        })),

      updateTaskContent: (id, data) =>
          set(state => ({
            tasks: state.tasks.map(task => {
              if (task.id !== id) return task

              if (task.status === 'SUCCESS' && data.status === 'SUCCESS') return task

              // 如果是 markdown 字符串，封装为版本
              if (typeof data.markdown === 'string') {
                const prev = task.markdown
                const newVersion: Markdown = {
                  ver_id: `${task.id}-${uuidv4()}`,
                  content: data.markdown,
                  style: task.formData.style || '',
                  model_name: task.formData.model_name || '',
                  created_at: new Date().toISOString(),
                }

                let updatedMarkdown: Markdown[]
                if (Array.isArray(prev)) {
                  updatedMarkdown = [newVersion, ...prev]
                } else {
                  updatedMarkdown = [
                    newVersion,
                    ...(typeof prev === 'string' && prev
                        ? [{
                          ver_id: `${task.id}-${uuidv4()}`,
                          content: prev,
                          style: task.formData.style || '',
                          model_name: task.formData.model_name || '',
                          created_at: new Date().toISOString(),
                        }]
                        : []),
                  ]
                }

                return {
                  ...task,
                  ...data,
                  markdown: updatedMarkdown,
                }
              }

              return { ...task, ...data }
            }),
          })),


      getCurrentTask: () => {
        const currentTaskId = get().currentTaskId
        return get().tasks.find(task => task.id === currentTaskId) || null
      },
      retryTask: async (id: string, payload?: TaskFormData) => {

        if (!id){
          toast.error('任务不存在')
          return
        }
        const task = get().tasks.find(task => task.id === id)
        console.log('retry',task)
        if (!task) return

        const newFormData = payload || task.formData
        await generateNote({
          ...newFormData,
          task_id: id,
        })

        set(state => ({
          tasks: state.tasks.map(t =>
              t.id === id
                  ? {
                    ...t,
                    formData: newFormData, // ✅ 显式更新 formData
                    status: 'PENDING',
                  }
                  : t
          ),
        }))
      },


      removeTask: async id => {
        // 更新 Zustand 状态
        set(state => ({
          tasks: state.tasks.filter(task => task.id !== id),
          currentTaskId: state.currentTaskId === id ? null : state.currentTaskId,
        }))

        // 调用后端删除接口
        try {
          await delete_task(id)
        } catch (e) {
          console.error('后端删除失败:', e)
        }
      },

      clearTasks: () => set({ tasks: [], currentTaskId: null }),

      setCurrentTask: taskId => set({ currentTaskId: taskId }),
    }),
    {
      name: 'task-storage',
    }
  )
)
