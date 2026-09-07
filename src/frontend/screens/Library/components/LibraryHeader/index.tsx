import React, { useContext, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import ActionIcons from 'frontend/components/UI/ActionIcons'
import { GameInfo } from 'common/types'
import { getGameLibraryStats } from 'common/gameLibraryStats'
import LibraryStats from './LibraryStats'
import LibraryContext from '../../LibraryContext'
import './index.css'
import AddGameButton from '../AddGameButton'

type Props = {
  list: GameInfo[]
}

export default React.memo(function LibraryHeader({ list }: Props) {
  const { t } = useTranslation()
  const { showFavourites, stackCopies, setStackCopies } =
    useContext(LibraryContext)

  const stats = useMemo(() => getGameLibraryStats(list), [list])

  return (
    <h5 className="libraryHeader" data-tour="library-header">
      <div className="libraryHeaderWrapper">
        <span className="libraryTitle">
          {showFavourites
            ? t('favourites', 'Favourites')
            : t('title.allGames', 'All Games')}
          <LibraryStats stats={stats} />
          <AddGameButton data-tour="library-add-game" />
          <label className="stackCopiesToggle">
            <input
              type="checkbox"
              checked={stackCopies}
              onChange={(event) => setStackCopies(event.currentTarget.checked)}
            />
            {t('gameCopies.stack', 'Stack copies')}
          </label>
        </span>
        <ActionIcons />
      </div>
    </h5>
  )
})
