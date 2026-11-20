'use client';

import React from 'react';
import { SearchX, RotateCcw } from 'lucide-react';

interface EmptyStateProps {
  hasFilters: boolean;
  onClearFilters: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  hasFilters,
  onClearFilters,
}) => {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center shadow-sm">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400">
        <SearchX className="h-6 w-6" />
      </div>

      <h3 className="mt-4 text-base font-semibold text-slate-900">
        No matching job listings found
      </h3>

      <p className="mt-1.5 max-w-sm text-xs leading-relaxed text-slate-500">
        {hasFilters
          ? 'Try adjusting your search keywords, broadening your location selection, or clearing active filters.'
          : 'No jobs are currently available in the database matching this query.'}
      </p>

      {hasFilters && (
        <button
          onClick={onClearFilters}
          className="mt-5 inline-flex items-center gap-1.5 rounded-lg bg-indigo-50 px-3.5 py-2 text-xs font-semibold text-indigo-600 hover:bg-indigo-100 transition"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          <span>Clear All Filters</span>
        </button>
      )}
    </div>
  );
};
