import type { ArtifactTab } from "@/features/artifacts/types";

type Tab = { id: ArtifactTab; label: string; icon: React.ComponentType<{ className?: string }> };
export function ArtifactTabs({ tabs, visibleTabs, activeTab, onChange }: { tabs: Tab[]; visibleTabs: Tab[]; activeTab: ArtifactTab; onChange: (tab: ArtifactTab) => void }) { return <div className="flex flex-wrap gap-2 rounded-xl border border-slate-200 bg-white p-2">{visibleTabs.map((tab) => <button key={tab.id} type="button" onClick={() => onChange(tab.id)} className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition ${activeTab === tab.id ? "bg-blue-50 font-semibold text-blue-700" : "text-slate-600 hover:bg-slate-100"}`}><tab.icon className="h-4 w-4" />{tab.label}</button>)}</div>; }
