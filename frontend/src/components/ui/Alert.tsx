import { ReactNode } from 'react'
import { AlertCircle, CheckCircle, Info, XCircle, X } from 'lucide-react'

interface AlertProps {
  type: 'info' | 'success' | 'warning' | 'error'
  title?: string
  children: ReactNode
  onClose?: () => void
  className?: string
}

export default function Alert({ type, title, children, onClose, className = '' }: AlertProps) {
  const styles = {
    info: {
      bg: 'bg-blue-50 dark:bg-blue-900/20',
      border: 'border-blue-200 dark:border-blue-800',
      text: 'text-blue-700 dark:text-blue-300',
      icon: Info,
    },
    success: {
      bg: 'bg-green-50 dark:bg-green-900/20',
      border: 'border-green-200 dark:border-green-800',
      text: 'text-green-700 dark:text-green-300',
      icon: CheckCircle,
    },
    warning: {
      bg: 'bg-yellow-50 dark:bg-yellow-900/20',
      border: 'border-yellow-200 dark:border-yellow-800',
      text: 'text-yellow-700 dark:text-yellow-300',
      icon: AlertCircle,
    },
    error: {
      bg: 'bg-red-50 dark:bg-red-900/20',
      border: 'border-red-200 dark:border-red-800',
      text: 'text-red-700 dark:text-red-300',
      icon: XCircle,
    },
  }

  const { bg, border, text, icon: Icon } = styles[type]

  return (
    <div className={`${bg} ${border} border rounded-lg p-4 relative ${className}`}>
      <div className="flex">
        <Icon className={`w-5 h-5 ${text} flex-shrink-0`} />
        <div className="ml-3 flex-1">
          {title && (
            <h4 className={`text-sm font-medium ${text}`}>{title}</h4>
          )}
          <div className={`text-sm ${text} ${title ? 'mt-1' : ''}`}>
            {children}
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className={`ml-3 ${text} hover:opacity-70 transition-opacity`}
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  )
}
