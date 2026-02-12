import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useParams, useNavigate } from 'react-router-dom'
import { useProviderStore } from '@/store/providerStore'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { testConnection, deleteModelById } from '@/services/model.ts'
import { ModelSelector } from '@/components/Form/modelForm/ModelSelector.tsx'
import { Tag } from 'antd'
import { useModelStore } from '@/store/modelStore'

// ✅ Provider表单schema
const ProviderSchema = z.object({
  name: z.string().min(2, '名称不能少于 2 个字符'),
  apiKey: z.string().optional(),
  baseUrl: z.string().url('必须是合法 URL'),
  type: z.string(),
})

type ProviderFormValues = z.infer<typeof ProviderSchema>

interface EnabledModel {
  id: number
  model_name: string
}
const ProviderForm = ({ isCreate = false }: { isCreate?: boolean }) => {
  const { id } = useParams()
  const navigate = useNavigate()
  const isEditMode = !isCreate

  const loadProviderById = useProviderStore(state => state.loadProviderById)
  const updateProvider = useProviderStore(state => state.updateProvider)
  const addNewProvider = useProviderStore(state => state.addNewProvider)
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState(false)
  const [isBuiltIn, setIsBuiltIn] = useState(false)
  const loadModelsById = useModelStore(state => state.loadModelsById)
  const [models, setModels] = useState<EnabledModel[]>([])
  const providerForm = useForm<ProviderFormValues>({
    resolver: zodResolver(ProviderSchema),
    defaultValues: {
      name: '',
      apiKey: '',
      baseUrl: '',
      type: 'custom',
    },
  })

  useEffect(() => {
    const load = async () => {
      if (isEditMode && id) {
        const data = await loadProviderById(id)
        providerForm.reset(data)
        setIsBuiltIn(data.type === 'built-in')
        
        // 只有在编辑模式且 id 有效时才加载模型列表
        const models = await loadModelsById(id)
        if (models) {
          console.log('🔧 模型列表:', models)
          setModels(models)
        }
      } else {
        providerForm.reset({
          name: '',
          apiKey: '',
          baseUrl: '',
          type: 'custom',
        })
        setIsBuiltIn(false)
        setModels([]) // 创建模式下清空模型列表
      }
      setLoading(false)
    }
    load()
  }, [id, isEditMode, loadModelsById, loadProviderById, providerForm])
  const handelDelete = async (modelId: number) => {
    if (!window.confirm('确定要删除这个模型吗？')) return

    try {
      const res = await deleteModelById(modelId)
      console.log('🔧 删除结果:', res)

      toast.success('删除成功')

    } catch {
      toast.error('删除异常')
    }
  }
  // 测试连通性
  const handleTest = async () => {
    const values = providerForm.getValues()
    if (!values.apiKey || !values.baseUrl) {
      toast.error('请填写 API Key 和 Base URL')
      return
    }
    try {
      if (!id){
        toast.error('请先保存供应商信息')
        return
      }
      setTesting(true)
      await testConnection({
        id
      })

        toast.success('测试连通性成功 🎉')

    } catch (error) {
      const message = error instanceof Error ? error.message : '未知错误'
      toast.error(`连接失败: ${message}`)
      // toast.error('测试连通性异常')
    } finally {
      setTesting(false)
    }
  }

  // 保存Provider信息
  const onProviderSubmit = async (values: ProviderFormValues) => {
    if (isEditMode && id) {
      await updateProvider({ ...values, id })
      toast.success('更新供应商成功')
    } else {
      try {
        const newId = await addNewProvider({ ...values })
        if (newId) {
          toast.success('新增供应商成功')
          // 导航到新创建的供应商页面，确保模型列表可以正确获取
          navigate(`/settings/model/${newId}`)
        } else {
          toast.error('创建供应商失败：未返回有效 ID')
        }
      } catch (error) {
        console.error('创建供应商失败:', error)
        toast.error('创建供应商失败')
      }
    }
  }

  if (loading) return <div className="p-4">加载中...</div>

  return (
    <div className="flex flex-col gap-8 p-4">
      {/* Provider信息表单 */}
      <Form {...providerForm}>
        <form
          onSubmit={providerForm.handleSubmit(onProviderSubmit)}
          className="flex max-w-xl flex-col gap-4"
        >
          <div className="text-lg font-bold">
            {isEditMode ? '编辑模型供应商' : '新增模型供应商'}
          </div>
          {!isBuiltIn && (
            <div className="text-sm text-red-500 italic">
              自定义模型供应商需要确保兼容 OpenAI SDK
            </div>
          )}
          <FormField
            control={providerForm.control}
            name="name"
            render={({ field }) => (
              <FormItem className="flex items-center gap-4">
                <FormLabel className="w-24 text-right">名称</FormLabel>
                <FormControl>
                  <Input {...field} disabled={isBuiltIn} className="flex-1" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={providerForm.control}
            name="apiKey"
            render={({ field }) => (
              <FormItem className="flex items-center gap-4">
                <FormLabel className="w-24 text-right">API Key</FormLabel>
                <FormControl>
                  <Input {...field} className="flex-1" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={providerForm.control}
            name="baseUrl"
            render={({ field }) => (
              <FormItem className="flex items-center gap-4">
                <FormLabel className="w-24 text-right">API地址</FormLabel>
                <FormControl>
                  <Input {...field} className="flex-1" />
                </FormControl>
                <Button type="button" onClick={handleTest} variant="ghost" disabled={testing}>
                  {testing ? '测试中...' : '测试连通性'}
                </Button>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={providerForm.control}
            name="type"
            render={({ field }) => (
              <FormItem className="flex items-center gap-4">
                <FormLabel className="w-24 text-right">类型</FormLabel>
                <FormControl>
                  <Input {...field} disabled className="flex-1" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <div className="pt-2">
            <Button type="submit" disabled={!providerForm.formState.isDirty}>
              {isEditMode ? '保存修改' : '保存创建'}
            </Button>
          </div>
        </form>
      </Form>

      {/* 模型信息表单 */}
      <div className="flex max-w-xl flex-col gap-4">
        <div className="flex flex-col gap-2">
          <span className="font-bold">模型列表</span>
          <div className={'flex flex-col gap-2 rounded bg-[#FEF0F0] p-2.5'}>
            <h2 className={'font-bold'}>注意!</h2>
            <span>请确保已经保存供应商信息,以及通过测试连通性.</span>
          </div>
          {id ? (
            <ModelSelector providerId={id} />
          ) : (
            <div className="text-sm text-gray-500">请先保存供应商信息后再添加模型</div>
          )}

          {/*<datalist id="model-options">*/}
          {/*  {modelOptions.map(model => (*/}
          {/*    <option key={model.id + '1'} value={model.id} />*/}
          {/*  ))}*/}
          {/*</datalist>*/}
        </div>
        <div className="flex flex-col gap-2">
          <span className="font-bold">已启用模型</span>
          <div className={'flex flex-wrap gap-2 rounded  p-2.5'}>
            {
              models && models.map(model => {
                return (
                  <Tag
                    onClose={() => {
                      handelDelete(model.id)
                    }}
                    key={model.id}
                    closable
                    color={'green'}
                  >
                    {model.model_name}
                  </Tag>

                )
              })
            }

          </div>
          {/*<ModelSelector providerId={id!} />*/}

          {/*<datalist id="model-options">*/}
          {/*  {modelOptions.map(model => (*/}
          {/*    <option key={model.id + '1'} value={model.id} />*/}
          {/*  ))}*/}
          {/*</datalist>*/}
        </div>
      </div>
    </div>
  )
}

export default ProviderForm
