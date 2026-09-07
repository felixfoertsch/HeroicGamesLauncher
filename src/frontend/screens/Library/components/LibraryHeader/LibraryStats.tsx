import { useMemo, useState } from 'react'
import Tooltip from '@mui/material/Tooltip'
import { useTranslation } from 'react-i18next'
import type { Runner } from 'common/types'
import type { GameLibraryStats } from 'common/gameLibraryStats'

interface Props {
  stats: GameLibraryStats
}

const storeOrder: readonly Runner[] = [
  'legendary',
  'gog',
  'nile',
  'zoom',
  'sideload'
]

export default function LibraryStats({ stats }: Props) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const numberFormat = useMemo(
    // Heroic locale IDs include pt_BR, nb_NO and zh_Hans; Intl uses hyphens.
    () =>
      new Intl.NumberFormat(
        (i18n.resolvedLanguage || i18n.language)?.replace(/_/g, '-')
      ),
    [i18n.resolvedLanguage, i18n.language]
  )
  const sources: Record<Runner, string> = {
    legendary: 'Epic Games',
    gog: 'GOG',
    nile: 'Amazon Games',
    zoom: 'Zoom Platform',
    sideload: t('libraryStats.sideloaded', 'Sideloaded')
  }
  const rows = [
    [t('libraryStats.games', 'Unique games'), stats.games],
    [t('libraryStats.copies', 'Total copies'), stats.copies],
    [
      t('libraryStats.multiStore', 'Games on multiple stores'),
      stats.multiStoreGames
    ],
    [
      t('libraryStats.extraCopies', 'Extra copies across stores'),
      stats.extraCopies
    ]
  ] as const

  return (
    <Tooltip
      describeChild
      placement="bottom-start"
      open={open}
      onOpen={() => setOpen(true)}
      onClose={() => setOpen(false)}
      leaveDelay={150}
      classes={{ tooltip: 'libraryStatsPopover' }}
      title={
        <div>
          <p className="libraryStatsHeading">
            {t('libraryStats.title', 'Library overview')}
          </p>
          <p className="libraryStatsScope">
            {t(
              'libraryStats.scope',
              'Current view, including search and filters.'
            )}
          </p>
          <dl className="libraryStatsNumbers">
            {rows.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{numberFormat.format(value)}</dd>
              </div>
            ))}
          </dl>
          <p className="libraryStatsHeading">
            {t('libraryStats.bySource', 'Copies by source')}
          </p>
          {stats.copies > 0 ? (
            <dl className="libraryStatsNumbers">
              {storeOrder
                .filter((runner) => stats.copiesByRunner[runner] > 0)
                .map((runner) => (
                  <div key={runner}>
                    <dt>{sources[runner]}</dt>
                    <dd>{numberFormat.format(stats.copiesByRunner[runner])}</dd>
                  </div>
                ))}
            </dl>
          ) : (
            <p className="libraryStatsScope">
              {t('libraryStats.empty', 'No games match this view.')}
            </p>
          )}
          <p className="libraryStatsExplanation">
            {t(
              'libraryStats.explanation',
              'Extra copies = total copies − unique games. Matching follows the library’s title and edition rules.'
            )}
          </p>
        </div>
      }
    >
      <button
        type="button"
        className="numberOfgames"
        aria-label={t('libraryStats.show', {
          defaultValue: '{{total}} — show library overview',
          total: numberFormat.format(stats.games)
        })}
        onClick={() => setOpen(true)}
      >
        {numberFormat.format(stats.games)}
      </button>
    </Tooltip>
  )
}
