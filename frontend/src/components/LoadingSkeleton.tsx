'use client';

import React from 'react';

export const LoadingSkeleton: React.FC = () => {
  return (
    <div className="space-y-4">
      {[1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm animate-pulse"
        >
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center gap-2">
              <div className="h-5 w-32 rounded-md bg-slate-100" />
              <div className="h-5 w-20 rounded-md bg-slate-100" />
            </div>
            <div className="h-4 w-16 rounded bg-slate-100" />
          </div>

          <div className="mt-3.5 space-y-2">
            <div className="h-5 w-3/4 rounded bg-slate-200" />
            <div className="flex gap-4">
              <div className="h-4 w-28 rounded bg-slate-100" />
              <div className="h-4 w-24 rounded bg-slate-100" />
            </div>
          </div>

          <div className="mt-3 space-y-1.5">
            <div className="h-3 w-full rounded bg-slate-100" />
            <div className="h-3 w-5/6 rounded bg-slate-100" />
          </div>

          <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-3.5">
            <div className="h-4 w-24 rounded bg-slate-100" />
            <div className="h-7 w-24 rounded-lg bg-indigo-100" />
          </div>
        </div>
      ))}
    </div>
  );
};
