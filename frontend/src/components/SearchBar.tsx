'use client';

import React from 'react';
import { Search, X, ArrowUpDown } from 'lucide-react';

interface SearchBarProps {
  query: string;
  onQueryChange: (q: string) => void;
  sortBy: 'recent' | 'title' | 'company';
  onSortByChange: (sort: 'recent' | 'title' | 'company') => void;
  totalResults: number;
  isLoading: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({
  query,
  onQueryChange,
  sortBy,
  onSortByChange,
  totalResults,
  isLoading,
}) => {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      {/* Search Input Field */}
      <div className="relative flex-1">
        <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
          <Search className="h-4 w-4" />
        </div>
        <input
          type="text"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Search by role, company, or tech stack (e.g. Python, React, Bangalore)..."
          className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-10 text-sm text-slate-900 placeholder:text-slate-400 shadow-sm transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        {query && (
          <button
            onClick={() => onQueryChange('')}
            className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-600"
            title="Clear search"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Sorting Control */}
      <div className="flex items-center justify-between gap-3 sm:justify-end">
        <span className="text-xs text-slate-500 font-medium">
          {isLoading ? (
            <span className="animate-pulse">Loading jobs...</span>
          ) : (
            <span>
              <strong className="text-slate-900 font-semibold">{totalResults}</strong> jobs found
            </span>
          )}
        </span>

        <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 shadow-sm">
          <ArrowUpDown className="h-3.5 w-3.5 text-slate-400" />
          <select
            value={sortBy}
            onChange={(e) => onSortByChange(e.target.value as 'recent' | 'title' | 'company')}
            className="bg-transparent text-xs font-medium text-slate-700 focus:outline-none cursor-pointer"
          >
            <option value="recent">Most Recent</option>
            <option value="title">Job Title (A–Z)</option>
            <option value="company">Company (A–Z)</option>
          </select>
        </div>
      </div>
    </div>
  );
};
