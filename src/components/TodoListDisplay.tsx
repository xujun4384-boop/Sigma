import type { TodoListData } from './ChatPanel'
import { useTranslation } from '../i18n/I18nContext'
import './TodoListDisplay.css'

interface Props {
  todolist: TodoListData
}

export default function TodoListDisplay({ todolist }: Props) {
  const { t } = useTranslation()
  const { todos, total, completed } = todolist
  const progress = total > 0 ? Math.round((completed / total) * 100) : 0
  const allDone = total > 0 && completed === total

  return (
    <div className={`todolist ${allDone ? 'todolist--done' : ''}`}>
      <div className="todolist__header">
        <span className="todolist__title">{t("todo.tasks")}</span>
        <span className={`todolist__badge ${allDone ? 'todolist__badge--done' : ''}`}>
          {completed}/{total}
        </span>
      </div>

      <div className="todolist__items">
        {todos.map((item, i) => (
          <div
            key={item.id || i}
            className={`todolist__item todolist__item--${item.status}`}
          >
            <span className={`todolist__item-status todolist__item-status--${item.status}`}>
              {item.status === 'completed' ? '✓' : item.status === 'in_progress' ? '›' : '○'}
            </span>
            <span className="todolist__item-content">{item.content}</span>
            <span className={`todolist__item-priority todolist__item-priority--${item.priority}`}>
              {item.priority}
            </span>
          </div>
        ))}
      </div>

      <div className="todolist__progress">
        <div
          className={`todolist__progress-bar ${allDone ? 'todolist__progress-bar--done' : ''}`}
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  )
}
