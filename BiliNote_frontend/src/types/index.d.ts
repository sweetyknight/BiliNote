export interface IProvider {
  id: string
  name: string
  logo: string
  type: string
  apiKey: string
  baseUrl: string
  enabled: number
  providerType?: string  // API 类型: 'openai' 或 'anthropic'
}
export interface IResponse<T> {
  code: number
  data:T
  msg: string
}