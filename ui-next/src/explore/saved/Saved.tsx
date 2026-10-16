import { useState } from 'react';
import type { Confirm } from '@aunoo/shell';
import { loadStarred, saveStarred } from '../feed/api';
import { ArticleSheet, type SheetTarget } from '../feed/ArticleSheet';
import { PromoteDialog, type PromoteArticle } from '../feed/PromoteDialog';
import { SignalReports } from '../agents/SignalReports';
import { Articles } from './Articles';
import { EmergingTopics } from './EmergingTopics';
import { Narratives } from './Narratives';
import { Podcasts } from './Podcasts';
import { SavedIncidents } from './SavedIncidents';

export interface SavedProps {
  /** The single topic picked in the filter bar, or undefined for all */
  topic?: string;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
  /** Opens another Explore tab (a tracked emerging topic opens Emerging Topics) */
  goToTab: (tabId: string) => void;
}

/*
 * Everything kept for later, in the old Saved tab's order (ui/src/pages/NewsFeedPage.tsx,
 * currentTab === 'saved'): starred articles, saved incidents, saved narratives, tracked emerging
 * topics, saved podcasts and the observer agents' saved reports. Articles open in the shared
 * details sheet.
 */
export function Saved({ topic, notify, askConfirm, goToTab }: SavedProps) {
  const [starred, setStarred] = useState<string[]>(loadStarred);
  const [sheet, setSheet] = useState<SheetTarget | null>(null);
  const [promote, setPromote] = useState<PromoteArticle | null>(null);

  const setStars = (next: string[]) => {
    saveStarred(next);
    setStarred(next);
  };
  const toggleStar = (uri: string) => setStars(starred.includes(uri) ? starred.filter((u) => u !== uri) : [...starred, uri]);
  const openArticle = (a: { uri: string; title?: string }) => setSheet({ article: { uri: a.uri, title: a.title } });

  return (
    <>
      <Articles starred={starred} onUnstar={(uri) => setStars(starred.filter((u) => u !== uri))} openArticle={openArticle} notify={notify} />
      <SavedIncidents topic={topic} notify={notify} askConfirm={askConfirm} openArticle={openArticle} />
      <Narratives notify={notify} askConfirm={askConfirm} />
      <EmergingTopics notify={notify} onOpen={() => goToTab('emerging-topics')} />
      <Podcasts notify={notify} askConfirm={askConfirm} />
      <SignalReports topic={topic} notify={notify} askConfirm={askConfirm} headingLevel={2} />

      <ArticleSheet
        target={sheet}
        onClose={() => setSheet(null)}
        onOpenRelated={(uri) => setSheet({ article: { uri } })}
        starred={starred}
        onToggleStar={toggleStar}
        onPromote={setPromote}
        notify={notify}
      />
      <PromoteDialog article={promote} topic={topic} onOpenChange={(o) => !o && setPromote(null)} onDone={() => undefined} notify={notify} />
    </>
  );
}
