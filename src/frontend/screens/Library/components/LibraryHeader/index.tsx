import React, {
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState
} from 'react'
import { useTranslation } from 'react-i18next'
import ActionIcons from 'frontend/components/UI/ActionIcons'
import { GameInfo } from 'common/types'
import { summarizeGameCopies } from 'common/gameStack'
import { getStoreName } from 'frontend/helpers'
import LibraryContext from '../../LibraryContext'
import './index.css'
import AddGameButton from '../AddGameButton'

type Props = {
  list: GameInfo[]
}

export default React.memo(function LibraryHeader({ list }: Props) {
  const { t } = useTranslation()
  const { showFavourites } = useContext(LibraryContext)
  const summary = useMemo(() => summarizeGameCopies(list ?? []), [list])
  const id = useId()
  const [open, setOpen] = useState(false)
  const label = t('librarySummary.title', 'Library summary')
  const popover = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const element = popover.current
    const updateOpen = () => setOpen(element?.matches(':popover-open') ?? false)
    element?.addEventListener('toggle', updateOpen)
    return () => element?.removeEventListener('toggle', updateOpen)
  }, [])

  return (
    <h5 className="libraryHeader" data-tour="library-header">
      <div className="libraryHeaderWrapper">
        <span className="libraryTitle">
          {showFavourites
            ? t('favourites', 'Favourites')
            : t('title.allGames', 'All Games')}
          <button
            type="button"
            className="numberOfgames librarySummaryButton"
            aria-label={label}
            aria-expanded={open}
            aria-controls={id}
            {...{ popovertarget: id }}
          >
            {summary.copies}
          </button>
          <div
            id={id}
            className="librarySummary"
            role="region"
            aria-label={label}
            {...{ popover: 'auto' }}
            ref={popover}
          >
            <strong>{label}</strong>
            <p>
              {t(
                'librarySummary.scope',
                'Counts reflect current library filters. DLC is excluded.'
              )}
            </p>
            <dl>
              {Array.from(summary.stores, ([runner, count]) => (
                <div key={runner}>
                  <dt>{getStoreName(runner, t('Other'))}</dt>
                  <dd>{count}</dd>
                </div>
              ))}
            </dl>
            <dl className="librarySummaryTotals">
              {[
                [
                  t('librarySummary.copies', 'Total store copies'),
                  summary.copies
                ],
                [t('librarySummary.unique', 'Unique games'), summary.unique],
                [
                  t('librarySummary.duplicates', 'Multi-store games'),
                  summary.duplicated
                ],
                [
                  t('librarySummary.extra', 'Extra copies'),
                  summary.extraCopies
                ],
                [
                  t('librarySummary.installed', 'Installed games'),
                  summary.installed
                ]
              ].map(([name, count]) => (
                <div key={name}>
                  <dt>{name}</dt>
                  <dd>{count}</dd>
                </div>
              ))}
            </dl>
            <p>
              {t(
                'librarySummary.matching',
                'Duplicates use matching store titles. Different editions stay separate; installations and settings are never merged.'
              )}
            </p>
          </div>
          <AddGameButton data-tour="library-add-game" />
        </span>
        <ActionIcons />
      </div>
    </h5>
  )
})
