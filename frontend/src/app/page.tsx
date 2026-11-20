'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Navbar,
} from '@/components/Navbar';
import { JobCard } from '@/components/JobCard';
import { SearchBar } from '@/components/SearchBar';
import { FilterSidebar } from '@/components/FilterSidebar';
import { Pagination } from '@/components/Pagination';
import { AnalyticsView } from '@/components/AnalyticsView';
import { LoadingSkeleton } from '@/components/LoadingSkeleton';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { useDebounce } from '@/hooks/useDebounce';
import {
  fetchHealth,
  fetchJobs,
  fetchJobFilters,
  fetchAnalytics,
  ApiError,
} from '@/lib/api';
import {
  JobListResponse,
  FilterFacets,
  AnalyticsResponse,
  HealthResponse,
} from '@/types/api';
import { SlidersHorizontal, X } from 'lucide-react';

export default function Home() {
  // Navigation State
  const [activeTab, setActiveTab] = useState<'jobs' | 'analytics'>('jobs');

  // Search & Filtering States
  const [queryInput, setQueryInput] = useState<string>('');
  const debouncedQuery = useDebounce<string>(queryInput, 400);

  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [selectedCities, setSelectedCities] = useState<string[]>([]);
  const [selectedJobTypes, setSelectedJobTypes] = useState<string[]>([]);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [fresherOnly, setFresherOnly] = useState<boolean>(false);
  const [fresherStatus, setFresherStatus] = useState<
    'fresher_friendly' | 'not_fresher_friendly' | 'uncertain' | 'pending' | ''
  >('');
  const [sortBy, setSortBy] = useState<'recent' | 'title' | 'company'>('recent');
  const [page, setPage] = useState<number>(1);
  const [limit] = useState<number>(12);

  // Mobile Drawer State
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState<boolean>(false);

  // Data States
  const [jobsData, setJobsData] = useState<JobListResponse | null>(null);
  const [facets, setFacets] = useState<FilterFacets | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  // Loading & Error States
  const [isLoadingJobs, setIsLoadingJobs] = useState<boolean>(true);
  const [isLoadingAnalytics, setIsLoadingAnalytics] = useState<boolean>(false);
  const [healthLoading, setHealthLoading] = useState<boolean>(false);
  const [jobError, setJobError] = useState<string | null>(null);

  // Compute active filters count
  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (fresherOnly) count += 1;
    if (fresherStatus) count += 1;
    count += selectedRoles.length;
    count += selectedCities.length;
    count += selectedJobTypes.length;
    count += selectedSources.length;
    return count;
  }, [
    fresherOnly,
    fresherStatus,
    selectedRoles,
    selectedCities,
    selectedJobTypes,
    selectedSources,
  ]);

  // Load Health
  const loadHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      const data = await fetchHealth();
      setHealth(data);
    } catch {
      setHealth({
        status: 'degraded',
        database: 'unreachable',
        environment: 'development',
        pricing_tier: 'unknown',
      });
    } finally {
      setHealthLoading(false);
    }
  }, []);

  // Load Filter Facets
  const loadFacets = useCallback(async () => {
    try {
      const data = await fetchJobFilters();
      setFacets(data);
    } catch (err) {
      console.error('Failed to load filter facets:', err);
    }
  }, []);

  // Load Jobs
  const loadJobs = useCallback(async () => {
    setIsLoadingJobs(true);
    setJobError(null);
    try {
      const data = await fetchJobs({
        q: debouncedQuery,
        role: selectedRoles,
        city: selectedCities,
        job_type: selectedJobTypes,
        source: selectedSources,
        fresher_only: fresherOnly,
        fresher_status: fresherStatus || undefined,
        sort_by: sortBy,
        page,
        limit,
      });
      setJobsData(data);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : 'Unable to retrieve jobs from backend.';
      setJobError(message);
    } finally {
      setIsLoadingJobs(false);
    }
  }, [
    debouncedQuery,
    selectedRoles,
    selectedCities,
    selectedJobTypes,
    selectedSources,
    fresherOnly,
    fresherStatus,
    sortBy,
    page,
    limit,
  ]);

  // Load Analytics
  const loadAnalytics = useCallback(async () => {
    setIsLoadingAnalytics(true);
    try {
      const data = await fetchAnalytics();
      setAnalytics(data);
    } catch (err) {
      console.error('Failed to load analytics telemetry:', err);
    } finally {
      setIsLoadingAnalytics(false);
    }
  }, []);

  // Initial mount load
  useEffect(() => {
    loadHealth();
    loadFacets();
  }, [loadHealth, loadFacets]);

  // Trigger jobs load when filters or search change
  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  // Trigger analytics load when tab switches
  useEffect(() => {
    if (activeTab === 'analytics') {
      loadAnalytics();
    }
  }, [activeTab, loadAnalytics]);

  // Reset page to 1 when filters or search query change
  const handleQueryChange = (q: string) => {
    setQueryInput(q);
    setPage(1);
  };

  const handleToggleRole = (role: string) => {
    setSelectedRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]
    );
    setPage(1);
  };

  const handleToggleCity = (city: string) => {
    setSelectedCities((prev) =>
      prev.includes(city) ? prev.filter((c) => c !== city) : [...prev, city]
    );
    setPage(1);
  };

  const handleToggleJobType = (type: string) => {
    setSelectedJobTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
    setPage(1);
  };

  const handleToggleSource = (source: string) => {
    setSelectedSources((prev) =>
      prev.includes(source) ? prev.filter((s) => s !== source) : [...prev, source]
    );
    setPage(1);
  };

  const handleToggleFresherOnly = (checked: boolean) => {
    setFresherOnly(checked);
    if (checked) {
      setFresherStatus('');
    }
    setPage(1);
  };

  const handleSelectFresherStatus = (
    status: 'fresher_friendly' | 'not_fresher_friendly' | 'uncertain' | 'pending' | ''
  ) => {
    setFresherStatus(status);
    if (status) {
      setFresherOnly(false);
    }
    setPage(1);
  };

  const handleClearAllFilters = () => {
    setSelectedRoles([]);
    setSelectedCities([]);
    setSelectedJobTypes([]);
    setSelectedSources([]);
    setFresherOnly(false);
    setFresherStatus('');
    setQueryInput('');
    setPage(1);
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans">
      {/* Navigation Header */}
      <Navbar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        health={health}
        healthLoading={healthLoading}
        onRefreshHealth={loadHealth}
      />

      {/* Main Content Area */}
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8">
        {activeTab === 'analytics' ? (
          <AnalyticsView analytics={analytics} isLoading={isLoadingAnalytics} />
        ) : (
          <div className="space-y-6">
            {/* Top Search & Filter Trigger Bar */}
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
              <SearchBar
                query={queryInput}
                onQueryChange={handleQueryChange}
                sortBy={sortBy}
                onSortByChange={(s) => {
                  setSortBy(s);
                  setPage(1);
                }}
                totalResults={jobsData?.total || 0}
                isLoading={isLoadingJobs}
              />

              {/* Mobile Filter Toggle Button */}
              <div className="mt-3.5 flex items-center justify-between border-t border-slate-100 pt-3 lg:hidden">
                <button
                  onClick={() => setMobileFiltersOpen(true)}
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 shadow-sm"
                >
                  <SlidersHorizontal className="h-3.5 w-3.5 text-indigo-600" />
                  <span>Filter Listings</span>
                  {activeFilterCount > 0 && (
                    <span className="rounded-full bg-indigo-600 px-1.5 py-0.2 text-[10px] text-white">
                      {activeFilterCount}
                    </span>
                  )}
                </button>

                {activeFilterCount > 0 && (
                  <button
                    onClick={handleClearAllFilters}
                    className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
                  >
                    Clear All
                  </button>
                )}
              </div>
            </div>

            {/* Layout Grid: Sidebar Filters + Jobs Column */}
            <div className="grid grid-cols-1 gap-8 lg:grid-cols-4">
              {/* Desktop Filter Sidebar */}
              <div className="hidden lg:block lg:col-span-1">
                <div className="sticky top-24 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <FilterSidebar
                    facets={facets}
                    selectedRoles={selectedRoles}
                    onToggleRole={handleToggleRole}
                    selectedCities={selectedCities}
                    onToggleCity={handleToggleCity}
                    selectedJobTypes={selectedJobTypes}
                    onToggleJobType={handleToggleJobType}
                    selectedSources={selectedSources}
                    onToggleSource={handleToggleSource}
                    fresherOnly={fresherOnly}
                    onToggleFresherOnly={handleToggleFresherOnly}
                    fresherStatus={fresherStatus}
                    onSelectFresherStatus={handleSelectFresherStatus}
                    onClearAllFilters={handleClearAllFilters}
                    activeFilterCount={activeFilterCount}
                  />
                </div>
              </div>

              {/* Jobs Stream Column */}
              <div className="lg:col-span-3 space-y-4">
                {/* Active Filter Chips Row */}
                {activeFilterCount > 0 && (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium text-slate-400">
                      Active Filters:
                    </span>

                    {fresherOnly && (
                      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-inset ring-emerald-600/20">
                        Confirmed Fresher Only
                        <button
                          onClick={() => setFresherOnly(false)}
                          className="hover:text-emerald-900"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    )}

                    {fresherStatus && (
                      <span className="inline-flex items-center gap-1 rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700 ring-1 ring-inset ring-indigo-600/20">
                        Status:{' '}
                        {fresherStatus === 'pending'
                          ? 'Unstated / Pending'
                          : fresherStatus === 'uncertain'
                          ? 'Model Uncertain'
                          : fresherStatus === 'fresher_friendly'
                          ? 'Fresher Friendly'
                          : fresherStatus === 'not_fresher_friendly'
                          ? 'Experienced'
                          : fresherStatus}
                        <button
                          onClick={() => setFresherStatus('')}
                          className="hover:text-indigo-900"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    )}

                    {selectedCities.map((c) => (
                      <span
                        key={c}
                        className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700"
                      >
                        {c}
                        <button
                          onClick={() => handleToggleCity(c)}
                          className="hover:text-slate-900"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}

                    {selectedRoles.map((r) => (
                      <span
                        key={r}
                        className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700"
                      >
                        {r}
                        <button
                          onClick={() => handleToggleRole(r)}
                          className="hover:text-slate-900"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}

                    {selectedSources.map((s) => (
                      <span
                        key={s}
                        className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium capitalize text-slate-700"
                      >
                        {s}
                        <button
                          onClick={() => handleToggleSource(s)}
                          className="hover:text-slate-900"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}

                    <button
                      onClick={handleClearAllFilters}
                      className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 ml-1"
                    >
                      Clear All
                    </button>
                  </div>
                )}

                {/* Job Cards List */}
                {isLoadingJobs ? (
                  <LoadingSkeleton />
                ) : jobError ? (
                  <ErrorState message={jobError} onRetry={loadJobs} />
                ) : jobsData?.jobs && jobsData.jobs.length > 0 ? (
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    {jobsData.jobs.map((job) => (
                      <JobCard key={job.id} job={job} />
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    hasFilters={activeFilterCount > 0 || !!queryInput}
                    onClearFilters={handleClearAllFilters}
                  />
                )}

                {/* Pagination Controls */}
                {jobsData && !isLoadingJobs && !jobError && (
                  <Pagination
                    currentPage={page}
                    totalPages={jobsData.pages}
                    totalItems={jobsData.total}
                    limit={limit}
                    onPageChange={(p) => {
                      setPage(p);
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                    isLoading={isLoadingJobs}
                  />
                )}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Mobile Filters Slide-Over Drawer */}
      {mobileFiltersOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div
            className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm"
            onClick={() => setMobileFiltersOpen(false)}
          />
          <div className="relative ml-auto flex h-full w-full max-w-xs flex-col overflow-y-auto bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <h2 className="text-base font-semibold text-slate-900">
                Filters & Criteria
              </h2>
              <button
                onClick={() => setMobileFiltersOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="mt-4 flex-1">
              <FilterSidebar
                facets={facets}
                selectedRoles={selectedRoles}
                onToggleRole={handleToggleRole}
                selectedCities={selectedCities}
                onToggleCity={handleToggleCity}
                selectedJobTypes={selectedJobTypes}
                onToggleJobType={handleToggleJobType}
                selectedSources={selectedSources}
                onToggleSource={handleToggleSource}
                fresherOnly={fresherOnly}
                onToggleFresherOnly={handleToggleFresherOnly}
                fresherStatus={fresherStatus}
                onSelectFresherStatus={handleSelectFresherStatus}
                onClearAllFilters={handleClearAllFilters}
                activeFilterCount={activeFilterCount}
              />
            </div>

            <div className="mt-6 border-t border-slate-100 pt-4">
              <button
                onClick={() => setMobileFiltersOpen(false)}
                className="w-full rounded-xl bg-indigo-600 py-2.5 text-center text-xs font-semibold text-white shadow-sm hover:bg-indigo-700"
              >
                Apply Filters & View Results
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Clean Footer */}
      <footer className="mt-auto border-t border-slate-200 bg-white py-6">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-4 text-xs text-slate-500 sm:flex-row sm:px-6 lg:px-8">
          <p>© 2026 Beep Platform. Genuine fresher and internship opportunities in India.</p>
          <div className="flex items-center gap-4 text-slate-400">
            <span>Hasjob Atom Feed</span>
            <span>•</span>
            <span>Remotive Public API</span>
            <span>•</span>
            <span>Zero Data Fabrication</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
