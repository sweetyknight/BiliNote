import { create } from 'zustand'
import { IProvider } from '@/types'
import {
  addProvider,
  getProviderById,
  getProviderList,
  updateProviderById,
  deleteProvider,
} from '@/services/model.ts'

// API 返回的供应商数据格式（蛇形命名）
interface ProviderApiResponse {
  id: string
  name: string
  logo: string
  api_key: string
  base_url: string
  type: string
  enabled: number
  provider_type?: string
}

interface ProviderStore {
  provider: IProvider[]
  setProvider: (provider: IProvider) => void
  setAllProviders: (providers: IProvider[]) => void
  getProviderById: (id: number) => IProvider | undefined
  getProviderList: () => IProvider[]
  fetchProviderList: () => Promise<void>
  loadProviderById: (id: string) => Promise<IProvider>
  addNewProvider: (provider: IProvider) => Promise<string>
  updateProvider: (provider: IProvider) => Promise<void>
  deleteProvider: (id: string) => Promise<boolean>
}

export const useProviderStore = create<ProviderStore>((set, get) => ({
  provider: [],

  // 添加或更新一个 provider
  setProvider: newProvider =>
    set(state => {
      const exists = state.provider.find(p => p.id === newProvider.id)
      if (exists) {
        return {
          provider: state.provider.map(p => (p.id === newProvider.id ? newProvider : p)),
        }
      } else {
        return { provider: [...state.provider, newProvider] }
      }
    }),

  // 设置整个 provider 列表
  setAllProviders: providers => set({ provider: providers }),

  // 按 ID 加载单个供应商
  loadProviderById: async (id: string) => {
    // 注意：request 拦截器已经解包，成功时直接返回 data 部分
    const item = await getProviderById(id) as ProviderApiResponse
    return {
      id: item.id,
      name: item.name,
      logo: item.logo,
      apiKey: item.api_key,
      baseUrl: item.base_url,
      type: item.type,
      enabled: item.enabled,
      providerType: item.provider_type,
    }
  },
  addNewProvider: async (provider: IProvider) => {
    const payload = {
      ...provider,
      api_key: provider.apiKey,
      base_url: provider.baseUrl,
      provider_type: provider.providerType || 'openai',
    }
    try {
      // 注意：request 拦截器已经解包，成功时直接返回 data 部分
      const newProviderId = await addProvider(payload)
      console.log('Provider added:', newProviderId)

      // 刷新供应商列表
      await get().fetchProviderList()
      return newProviderId
    } catch (error) {
      console.error('Error adding provider:', error)
      throw error
    }
  },
  // 按 id 获取单个 provider
  getProviderById: id => get().provider.find(p => p.id === id),
  updateProvider: async (provider: IProvider) => {
    try {
      const data = {
        ...provider,
        api_key: provider.apiKey,
        base_url: provider.baseUrl,
        provider_type: provider.providerType,
      }
      // 注意：request 拦截器已经解包，成功时直接返回 data 部分
      const result = await updateProviderById(data)
      console.log('Provider updated:', result)

      // 刷新供应商列表
      await get().fetchProviderList()
    } catch (error) {
      console.error('Error updating provider:', error)
      throw error
    }
  },
  getProviderList: () => get().provider,
  fetchProviderList: async () => {
    try {
      // 注意：request 拦截器已经解包，成功时直接返回 data 部分
      const providers = await getProviderList() as ProviderApiResponse[]
      set({
        provider: providers.map((item) => ({
          id: item.id,
          name: item.name,
          logo: item.logo,
          apiKey: item.api_key,
          baseUrl: item.base_url,
          type: item.type,
          enabled: item.enabled,
          providerType: item.provider_type,
        })),
      })
    } catch (error) {
      console.error('Error fetching provider list:', error)
    }
  },
  deleteProvider: async (id: string) => {
    try {
      await deleteProvider(id)
      // 从本地状态中移除
      set(state => ({
        provider: state.provider.filter(p => p.id !== id)
      }))
      return true
    } catch (error) {
      console.error('Error deleting provider:', error)
      return false
    }
  },
}))
