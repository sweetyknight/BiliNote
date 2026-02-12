import request from '@/utils/request'
import toast from 'react-hot-toast'

export const generateNote = async (data: {
  video_url: string
  platform: string
  quality: string
  model_name: string
  provider_id: string
  task_id?: string
  format: Array<string>
  style: string
  extras?: string
  video_understand?: boolean
  video_interval?: number
  grid_size: Array<number>
}) => {
  try {
    console.log('generateNote', data)
    const response = await request.post('/generate_note', data)

    if (!response) {
      if (response.data.msg) {
        toast.error(response.data.msg)
      }
      return null
    }
    toast.success('笔记生成任务已提交！')

    console.log('res', response)
    // 成功提示

    return response
  } catch (error: unknown) {
    console.error('❌ 请求出错', error)

    // 错误提示
    // toast.error('笔记生成失败，请稍后重试')

    throw error // 抛出错误以便调用方处理
  }
}

export const delete_task = async (task_id: string) => {
  try {
    const res = await request.post('/delete_task', { task_id })
    toast.success('任务已成功删除')
    return res
  } catch (e) {
    toast.error('请求异常，删除任务失败')
    console.error('❌ 删除任务失败:', e)
    throw e
  }
}

export const get_task_status = async (task_id: string) => {
  // 轮询请求使用更长的超时时间，避免在后端繁忙时误判
  return await request.get('/task_status/' + task_id, { timeout: 30000 })
}

/**
 * 获取所有历史笔记（从服务器端）
 * 用于加载批量脚本或其他方式生成的笔记
 */
export const get_note_history = async () => {
  try {
    const response = await request.get('/note_history')
    return response || []
  } catch (e) {
    console.error('❌ 获取历史笔记失败', e)
    return []
  }
}