import { Switch } from '@/components/ui/switch'
import { FC, useState } from 'react'
import styles from './index.module.css'
import { useNavigate, useParams } from 'react-router-dom'
import AILogo from '@/components/Form/modelForm/Icons'
import { useProviderStore } from '@/store/providerStore'
import { Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'

export interface IProviderCardProps {
  id: string
  providerName: string
  Icon: string
  enable: number
}
const ProviderCard: FC<IProviderCardProps> = ({
  providerName,
  Icon,
  id,
  enable,
}: IProviderCardProps) => {
  const navigate = useNavigate()
  const updateProvider = useProviderStore(state => state.updateProvider)
  const deleteProviderAction = useProviderStore(state => state.deleteProvider)
  const [isDeleting, setIsDeleting] = useState(false)

  const handleClick = () => {
    navigate(`/settings/model/${id}`)
  }
  const handleEnable = () => {
    console.log('enable', enable)
    updateProvider({
      id,
      enabled: enable == 1 ? 0 : 1,
    })
  }
  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm(`确定要删除供应商 "${providerName}" 吗？此操作不可恢复。`)) {
      return
    }
    try {
      setIsDeleting(true)
      const success = await deleteProviderAction(id)
      if (success) {
        toast.success('删除供应商成功')
        navigate('/settings/model')
      } else {
        toast.error('删除供应商失败')
      }
  } catch {
      toast.error('删除供应商异常')
    } finally {
      setIsDeleting(false)
    }
  }
  const { id: currentId } = useParams<{ id: string }>()
  const isActive = currentId === id
  return (
    <div
      onClick={() => {
        handleClick()
      }}
      className={
        styles.card +
        ' group flex h-14 items-center justify-between rounded border border-[#f3f3f3] p-2' +
        (isActive ? ' bg-[#F0F0F0] font-semibold text-emerald-600' : '')
      }
    >
      <div className="flex items-center text-lg">
        <div className="flex h-9 w-9 items-center">
          <AILogo name={Icon} />
        </div>
        <div className="font-semibold">{providerName}</div>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={handleDelete}
          disabled={isDeleting}
          className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-red-100 rounded text-red-500 hover:text-red-700"
          title="删除供应商"
        >
          <Trash2 size={18} />
        </button>
        <Switch
          onClick={e => {
            e.stopPropagation()
            handleEnable()
          }}
          checked={enable == 1}
        />
      </div>
    </div>
  )
}
export default ProviderCard
