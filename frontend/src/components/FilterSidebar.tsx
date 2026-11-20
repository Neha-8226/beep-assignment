'use client';

import React from 'react';
import {
  Filter,
  RotateCcw,
  Sparkles,
  MapPin,
  Briefcase,
  Layers,
  Check,
} from 'lucide-react';
import { FilterFacets } from '@/types/api';

interface FilterSidebarProps {
  facets: FilterFacets | null;
  selectedRoles: string[];
  onToggleRole: (role: string) => void;
  selectedCities: string[];
  onToggleCity: (city: string) => void;
  selectedJobTypes: string[];
  onToggleJobType: (type: string) => void;
  selectedSources: string[];
  onToggleSource: (source: string) => void;
  fresherOnly: boolean;
  onToggleFresherOnly: (checked: boolean) => void;
  fresherStatus: 'fresher_friendly' | 'not_fresher_friendly' | 'uncertain' | 'pending' | '';
  onSelectFresherStatus: (status: 'fresher_friendly' | 'not_fresher_friendly' | 'uncertain' | 'pending' | '') => void;
  onClearAllFilters: () => void;
  activeFilterCount: number;
}

export const FilterSidebar: React.FC<FilterSidebarProps> = ({
  facets,
  selectedRoles,
  onToggleRole,
  selectedCities,
  onToggleCity,
  selectedJobTypes,
  onToggleJobType,
  selectedSources,
  onToggleSource,
  fresherOnly,
  onToggleFresherOnly,
  fresherStatus,
  onSelectFresherStatus,
  onClearAllFilters,
  activeFilterCount,
}) => {
  return (
    <aside className="w-full space-y-6">
      {/* Filters Header & Clear All */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-slate-700" />
          <h2 className="text-sm font-semibold text-slate-900">Filters</h2>
          {activeFilterCount > 0 && (
            <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-indigo-600 text-xs font-semibold text-white">
              {activeFilterCount}
            </span>
          )}
        </div>

        {activeFilterCount > 0 && (
          <button
            onClick={onClearAllFilters}
            className="flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-800 transition"
          >
            <RotateCcw className="h-3 w-3" />
            <span>Reset All</span>
          </button>
        )}
      </div>

      {/* 1. Fresher Eligibility Filter */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Fresher Eligibility
          </h3>
        </div>

        {/* Quick Toggle: Confirmed Fresher Only */}
        <label className="flex cursor-pointer items-center justify-between rounded-lg border border-slate-200 bg-slate-50 p-2.5 transition hover:bg-slate-100">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-emerald-600" />
            <span className="text-xs font-medium text-slate-800">
              Confirmed Fresher Only
            </span>
          </div>
          <input
            type="checkbox"
            checked={fresherOnly}
            onChange={(e) => onToggleFresherOnly(e.target.checked)}
            className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-600"
          />
        </label>

        {/* Granular Status Select */}
        <div className="grid grid-cols-2 gap-1.5 pt-1">
          <button
            onClick={() => onSelectFresherStatus('')}
            className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
              fresherStatus === '' && !fresherOnly
                ? 'bg-slate-900 text-white'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            All Listings
          </button>
          <button
            onClick={() => onSelectFresherStatus('fresher_friendly')}
            className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
              fresherStatus === 'fresher_friendly' || fresherOnly
                ? 'bg-emerald-600 text-white'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            Fresher Friendly
          </button>
          <button
            onClick={() => onSelectFresherStatus('not_fresher_friendly')}
            className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
              fresherStatus === 'not_fresher_friendly'
                ? 'bg-rose-600 text-white'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            Experienced
          </button>
          <button
            onClick={() => onSelectFresherStatus('pending')}
            className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
              fresherStatus === 'pending'
                ? 'bg-amber-600 text-white'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            Unstated / Pending
          </button>
          <button
            onClick={() => onSelectFresherStatus('uncertain')}
            className={`col-span-2 rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
              fresherStatus === 'uncertain'
                ? 'bg-purple-600 text-white'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            Model Uncertain
          </button>
        </div>
      </div>

      {/* 2. Standardized Tech Hubs / Cities */}
      {facets?.cities && facets.cities.length > 0 && (
        <div className="space-y-2 border-t border-slate-100 pt-4">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <MapPin className="h-3.5 w-3.5" />
            <span>Locations</span>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {facets.cities.map((city) => {
              const isSelected = selectedCities.includes(city.name);
              return (
                <button
                  key={city.name}
                  onClick={() => onToggleCity(city.name)}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                    isSelected
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  {isSelected && <Check className="h-3 w-3" />}
                  <span>{city.name}</span>
                  <span
                    className={`rounded-full px-1.5 py-0.2 text-[10px] ${
                      isSelected ? 'bg-indigo-700 text-indigo-100' : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {city.count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* 3. Role Categories */}
      {facets?.roles && facets.roles.length > 0 && (
        <div className="space-y-2 border-t border-slate-100 pt-4">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <Briefcase className="h-3.5 w-3.5" />
            <span>Roles</span>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {facets.roles.map((role) => {
              const isSelected = selectedRoles.includes(role.name);
              return (
                <button
                  key={role.name}
                  onClick={() => onToggleRole(role.name)}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                    isSelected
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  {isSelected && <Check className="h-3 w-3" />}
                  <span>{role.name}</span>
                  <span
                    className={`rounded-full px-1.5 py-0.2 text-[10px] ${
                      isSelected ? 'bg-indigo-700 text-indigo-100' : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {role.count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* 4. Job Types */}
      {facets?.job_types && facets.job_types.length > 0 && (
        <div className="space-y-2 border-t border-slate-100 pt-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Job Types
          </h3>

          <div className="flex flex-wrap gap-1.5">
            {facets.job_types.map((type) => {
              const isSelected = selectedJobTypes.includes(type.name);
              return (
                <button
                  key={type.name}
                  onClick={() => onToggleJobType(type.name)}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                    isSelected
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  {isSelected && <Check className="h-3 w-3" />}
                  <span>{type.name}</span>
                  <span
                    className={`rounded-full px-1.5 py-0.2 text-[10px] ${
                      isSelected ? 'bg-indigo-700 text-indigo-100' : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {type.count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* 5. Ingestion Sources */}
      {facets?.sources && facets.sources.length > 0 && (
        <div className="space-y-2 border-t border-slate-100 pt-4">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <Layers className="h-3.5 w-3.5" />
            <span>Permitted Sources</span>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {facets.sources.map((source) => {
              const isSelected = selectedSources.includes(source.name);
              return (
                <button
                  key={source.name}
                  onClick={() => onToggleSource(source.name)}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium capitalize transition ${
                    isSelected
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  {isSelected && <Check className="h-3 w-3" />}
                  <span>{source.name}</span>
                  <span
                    className={`rounded-full px-1.5 py-0.2 text-[10px] ${
                      isSelected ? 'bg-indigo-700 text-indigo-100' : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {source.count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </aside>
  );
};
