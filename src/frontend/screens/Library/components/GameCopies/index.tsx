import './index.css'

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { GameInfo } from 'common/types'
import { getGameIdentity } from 'common/gameStack'
import { getStoreName } from 'frontend/helpers'
import StoreLogos from 'frontend/components/UI/StoreLogos'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader
} from 'frontend/components/UI/Dialog'

interface Props {
  copies: readonly GameInfo[]
  title: string
}

export default function GameCopies({ copies, title }: Props) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const onClose = () => setOpen(false)

  if (copies.length < 2) return null

  const label = t('gameCopies.show', {
    defaultValue: 'Show {{count}} copies of {{title}}',
    count: copies.length,
    title
  })

  return (
    <>
      <button
        type="button"
        className="gameCopiesBadge"
        title={label}
        aria-label={label}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation()
          setOpen(true)
        }}
      >
        {copies.length}
      </button>
      {open && (
        <Dialog onClose={onClose} showCloseButton className="gameCopiesDialog">
          <DialogHeader onClose={onClose}>
            {t('gameCopies.title', {
              defaultValue: 'Copies of {{title}}',
              title
            })}
          </DialogHeader>
          <DialogContent>
            <p>
              {t(
                'gameCopies.description',
                'Choose a store version to open its game page. Each copy keeps its own installation and settings.'
              )}
            </p>
            <ul className="gameCopiesList">
              {copies.map((gameInfo) => (
                <li key={getGameIdentity(gameInfo)}>
                  <Link
                    className="gameCopiesLink"
                    to={`/gamepage/${gameInfo.runner}/${gameInfo.app_name}`}
                    state={{ gameInfo }}
                    onClick={onClose}
                  >
                    <StoreLogos runner={gameInfo.runner} />
                    <span className="gameCopiesDetails">
                      <strong>
                        {getStoreName(gameInfo.runner, t('Other'))}
                      </strong>
                      <span>{gameInfo.overrides?.title || gameInfo.title}</span>
                    </span>
                    <span className="gameCopiesStatus">
                      {gameInfo.is_installed
                        ? t('gameCopies.installed', 'Installed')
                        : t('gameCopies.notInstalled', 'Not installed')}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </DialogContent>
          <DialogFooter>
            <button type="button" className="button outline" onClick={onClose}>
              {t('gamepage:box.close', 'Close')}
            </button>
          </DialogFooter>
        </Dialog>
      )}
    </>
  )
}
