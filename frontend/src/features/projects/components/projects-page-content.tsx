"use client";

import Link from "next/link";
import { Search, SlidersHorizontal, TrendingUp, Users, X } from "lucide-react";
import { useMemo, useState } from "react";

import { PROJECTS } from "@/features/projects/data";
import type { ProjectStatus } from "@/features/projects/types";

const statusOptions: Array<"All statuses" | ProjectStatus> = ["All statuses", "Active", "At Risk", "Completed"];
const sprintOptions = ["All sprints", ...new Set(PROJECTS.flatMap((project) => project.sprints.map((sprint) => sprint.name)))];
const moduleOptions = ["All modules", ...new Set(PROJECTS.map((project) => project.module))];
const sortOptions = [
  { value: "name-asc", label: "Name (A-Z)" },
  { value: "name-desc", label: "Name (Z-A)" },
  { value: "score-desc", label: "Score (Highest first)" },
  { value: "score-asc", label: "Score (Lowest first)" },
  { value: "completion-desc", label: "Completion (Highest first)" },
  { value: "completion-asc", label: "Completion (Lowest first)" },
  { value: "status-priority", label: "Status (At Risk first)" },
] as const;

type SortValue = (typeof sortOptions)[number]["value"];

type ProjectFilters = {
  teamName: string;
  status: "All statuses" | ProjectStatus;
  sprint: string;
  module: string;
  minScore: string;
  maxScore: string;
  minCompletion: string;
  maxCompletion: string;
  sortBy: SortValue;
};

const DEFAULT_FILTERS: ProjectFilters = {
  teamName: "",
  status: "All statuses",
  sprint: "All sprints",
  module: "All modules",
  minScore: "",
  maxScore: "",
  minCompletion: "",
  maxCompletion: "",
  sortBy: "name-asc",
};

function getStatusStyles(status: ProjectStatus) {
  if (status === "At Risk") {
    return "bg-rose-50 text-rose-600";
  }

  if (status === "Completed") {
    return "bg-slate-100 text-slate-600";
  }

  return "bg-emerald-50 text-emerald-600";
}

export default function ProjectsPageContent() {
  const [searchTerm, setSearchTerm] = useState("");
  const [isFilterModalOpen, setIsFilterModalOpen] = useState(false);
  const [appliedFilters, setAppliedFilters] = useState<ProjectFilters>(DEFAULT_FILTERS);
  const [draftFilters, setDraftFilters] = useState<ProjectFilters>(DEFAULT_FILTERS);

  const appliedFilterCount = useMemo(() => {
    let count = 0;
    if (appliedFilters.teamName.trim()) count += 1;
    if (appliedFilters.status !== "All statuses") count += 1;
    if (appliedFilters.sprint !== "All sprints") count += 1;
    if (appliedFilters.module !== "All modules") count += 1;
    if (appliedFilters.minScore !== "" || appliedFilters.maxScore !== "") count += 1;
    if (appliedFilters.minCompletion !== "" || appliedFilters.maxCompletion !== "") count += 1;
    if (appliedFilters.sortBy !== "name-asc") count += 1;
    return count;
  }, [appliedFilters]);

  function updateDraftFilter<K extends keyof ProjectFilters>(key: K, value: ProjectFilters[K]) {
    setDraftFilters((prev) => ({ ...prev, [key]: value }));
  }

  function parseRangeValue(value: string) {
    if (value.trim() === "") {
      return null;
    }
    const parsed = Number(value);
    return Number.isNaN(parsed) ? null : parsed;
  }

  function openFilterModal() {
    setDraftFilters(appliedFilters);
    setIsFilterModalOpen(true);
  }

  function applyFilters() {
    setAppliedFilters(draftFilters);
    setIsFilterModalOpen(false);
  }

  function clearDraftFilters() {
    setDraftFilters(DEFAULT_FILTERS);
  }

  function clearAppliedFilters() {
    setAppliedFilters(DEFAULT_FILTERS);
    setDraftFilters(DEFAULT_FILTERS);
  }

  const filteredProjects = useMemo(() => {
    const minScore = parseRangeValue(appliedFilters.minScore);
    const maxScore = parseRangeValue(appliedFilters.maxScore);
    const minCompletion = parseRangeValue(appliedFilters.minCompletion);
    const maxCompletion = parseRangeValue(appliedFilters.maxCompletion);

    const matches = PROJECTS.filter((project) => {
      const normalizedSearch = searchTerm.trim().toLowerCase();
      const normalizedTeamName = appliedFilters.teamName.trim().toLowerCase();
      const searchBlob = [project.name, project.teamName, project.module, ...project.sprints.map((sprint) => sprint.name)]
        .join(" ")
        .toLowerCase();

      const matchesSearch = normalizedSearch.length === 0 || searchBlob.includes(normalizedSearch);
      const matchesTeamName = normalizedTeamName.length === 0 || project.teamName.toLowerCase().includes(normalizedTeamName);
      const matchesStatus = appliedFilters.status === "All statuses" || project.status === appliedFilters.status;
      const matchesSprint =
        appliedFilters.sprint === "All sprints" || project.sprints.some((sprint) => sprint.name === appliedFilters.sprint);
      const matchesModule = appliedFilters.module === "All modules" || project.module === appliedFilters.module;
      const matchesMinScore = minScore === null || project.score >= minScore;
      const matchesMaxScore = maxScore === null || project.score <= maxScore;
      const matchesMinCompletion = minCompletion === null || project.completion >= minCompletion;
      const matchesMaxCompletion = maxCompletion === null || project.completion <= maxCompletion;

      return (
        matchesSearch &&
        matchesTeamName &&
        matchesStatus &&
        matchesSprint &&
        matchesModule &&
        matchesMinScore &&
        matchesMaxScore &&
        matchesMinCompletion &&
        matchesMaxCompletion
      );
    });

    const sorted = [...matches];

    sorted.sort((left, right) => {
      if (appliedFilters.sortBy === "name-desc") {
        return right.name.localeCompare(left.name);
      }

      if (appliedFilters.sortBy === "score-desc") {
        return right.score - left.score;
      }

      if (appliedFilters.sortBy === "score-asc") {
        return left.score - right.score;
      }

      if (appliedFilters.sortBy === "completion-desc") {
        return right.completion - left.completion;
      }

      if (appliedFilters.sortBy === "completion-asc") {
        return left.completion - right.completion;
      }

      if (appliedFilters.sortBy === "status-priority") {
        const rank: Record<ProjectStatus, number> = { "At Risk": 0, Active: 1, Completed: 2 };
        const statusDiff = rank[left.status] - rank[right.status];
        if (statusDiff !== 0) {
          return statusDiff;
        }
        return right.score - left.score;
      }

      return left.name.localeCompare(right.name);
    });

    return sorted;
  }, [searchTerm, appliedFilters]);

  return (
    <div className="space-y-5 p-8">
      <div>
        <h1 className="text-4xl font-bold tracking-tight text-blue-950">Projects</h1>
        <p className="mt-1 text-base text-slate-500">Manage and monitor all student projects</p>
      </div>

      <div className="space-y-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Search by project or team name..."
            className="h-11 w-full rounded-xl border border-slate-200 bg-white pl-11 pr-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2"
          />
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_220px_220px]">
          <div className="hidden items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm text-slate-500 md:flex">
            <SlidersHorizontal className="h-4 w-4" />
            {appliedFilterCount > 0 ? `${appliedFilterCount} filter(s) applied` : "No filters applied"}
          </div>

          <button
            type="button"
            onClick={openFilterModal}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 outline-none ring-blue-100 transition hover:bg-slate-50 focus:border-blue-300 focus:ring-2"
          >
            <SlidersHorizontal className="h-4 w-4" />
            Filter and Sort
          </button>

          <button
            type="button"
            onClick={clearAppliedFilters}
            className="inline-flex h-11 items-center justify-center rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 outline-none ring-blue-100 transition hover:bg-slate-50 focus:border-blue-300 focus:ring-2"
          >
            Reset filters
          </button>
        </div>
      </div>

      {isFilterModalOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Filter and sort projects</h2>
                <p className="text-sm text-slate-500">Adjust criteria, then apply to refresh the project list.</p>
              </div>
              <button
                type="button"
                onClick={() => setIsFilterModalOpen(false)}
                className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
                aria-label="Close filter modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 px-5 py-4 md:grid-cols-2">
              <label className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700">Team name</span>
                <input
                  type="text"
                  value={draftFilters.teamName}
                  onChange={(event) => updateDraftFilter("teamName", event.target.value)}
                  placeholder="e.g. Team Alpha"
                  className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2"
                />
              </label>

              <label className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700">Status</span>
                <select
                  value={draftFilters.status}
                  onChange={(event) => updateDraftFilter("status", event.target.value as "All statuses" | ProjectStatus)}
                  className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2"
                >
                  {statusOptions.map((statusOption) => (
                    <option key={statusOption} value={statusOption}>
                      {statusOption}
                    </option>
                  ))}
                </select>
              </label>

              <label className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700">Module</span>
                <select
                  value={draftFilters.module}
                  onChange={(event) => updateDraftFilter("module", event.target.value)}
                  className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2"
                >
                  {moduleOptions.map((moduleOption) => (
                    <option key={moduleOption} value={moduleOption}>
                      {moduleOption}
                    </option>
                  ))}
                </select>
              </label>

              <label className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700">Sprint</span>
                <select
                  value={draftFilters.sprint}
                  onChange={(event) => updateDraftFilter("sprint", event.target.value)}
                  className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2"
                >
                  {sprintOptions.map((sprintOption) => (
                    <option key={sprintOption} value={sprintOption}>
                      {sprintOption}
                    </option>
                  ))}
                </select>
              </label>

              <div className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700">Score range</span>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={draftFilters.minScore}
                    onChange={(event) => updateDraftFilter("minScore", event.target.value)}
                    placeholder="Min"
                    className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2"
                  />
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={draftFilters.maxScore}
                    onChange={(event) => updateDraftFilter("maxScore", event.target.value)}
                    placeholder="Max"
                    className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700">Completion range (%)</span>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={draftFilters.minCompletion}
                    onChange={(event) => updateDraftFilter("minCompletion", event.target.value)}
                    placeholder="Min"
                    className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2"
                  />
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={draftFilters.maxCompletion}
                    onChange={(event) => updateDraftFilter("maxCompletion", event.target.value)}
                    placeholder="Max"
                    className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2"
                  />
                </div>
              </div>

              <label className="space-y-1.5 md:col-span-2">
                <span className="text-sm font-medium text-slate-700">Sort by</span>
                <select
                  value={draftFilters.sortBy}
                  onChange={(event) => updateDraftFilter("sortBy", event.target.value as SortValue)}
                  className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2"
                >
                  {sortOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-4">
              <button
                type="button"
                onClick={clearDraftFilters}
                className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
              >
                Clear form
              </button>
              <button
                type="button"
                onClick={() => setIsFilterModalOpen(false)}
                className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={applyFilters}
                className="inline-flex h-10 items-center justify-center rounded-lg bg-blue-700 px-4 text-sm font-semibold text-white transition hover:bg-blue-800"
              >
                Apply filters
              </button>
            </div>
          </div>
        </div>
      )}

      {filteredProjects.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <h2 className="text-lg font-semibold text-slate-900">No projects matched your filters</h2>
          <p className="mt-1 text-sm text-slate-500">Try broadening your search, sprint, or status selection.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          {filteredProjects.map((project) => (
            <Link
              key={project.id}
              href={`/projects/${project.id}/sprints`}
              className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-md"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-3xl font-semibold leading-tight text-blue-950">{project.name}</h2>
                  <p className="mt-1 text-sm text-slate-500">{project.teamName}</p>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${getStatusStyles(project.status)}`}>{project.status}</span>
              </div>

              <p className="mt-4 text-sm text-slate-500">{project.module}</p>

              <div className="mt-4 flex items-center gap-3 text-slate-500">
                <Users className="h-4 w-4" />
                <div className="flex items-center">
                  {project.members.map((member) => (
                    <span
                      key={member}
                      className="-ml-1.5 flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-blue-100 text-xs font-semibold text-blue-700 first:ml-0"
                    >
                      {member}
                    </span>
                  ))}
                </div>
              </div>

              <div className="mt-5 flex items-center justify-between text-sm">
                <div className="flex items-center gap-1.5 font-semibold text-blue-900">
                  <TrendingUp className="h-4 w-4" />
                  {project.score}/100
                </div>
                <div className="text-slate-500">{project.completion}% complete</div>
              </div>

              <div className="mt-3 h-2 rounded-full bg-slate-200">
                <div className="h-full rounded-full bg-blue-700" style={{ width: `${project.completion}%` }} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
