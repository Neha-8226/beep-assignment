'use client';

import React from 'react';
import { Briefcase, BarChart3, RefreshCw } from 'lucide-react';
import { HealthResponse } from '@/types/api';

interface NavbarProps {
  activeTab: 'jobs' | 'analytics';
  onTabChange: (tab: 'jobs' | 'analytics') => void;
  health: HealthResponse | null;
  healthLoading: boolean;
  onRefreshHealth: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onTabChange,
  health,
  healthLoading,
  onRefreshHealth,
}) => {
  const isHealthy = health?.status === 'healthy';

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Brand Logo & Tagline */}
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
            <Briefcase className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xl font-bold tracking-tight text-slate-900">Beep</span>
              <span className="inline-flex items-center rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700 ring-1 ring-inset ring-indigo-600/10">
                Jobs India
              </span>
            </div>
            <p className="hidden text-xs text-slate-500 sm:block">
              AI-Curated Fresher & Internship Aggregator
            </p>
          </div>
        </div>

        {/* View Switcher Tabs */}
        <div className="flex items-center rounded-lg bg-slate-100 p-1">
          <button
            onClick={() => onTabChange('jobs')}
            className={`flex items-center gap-2 rounded-md px-3.5 py-1.5 text-sm font-medium transition-all ${
              activeTab === 'jobs'
                ? 'bg-white text-indigo-600 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Briefcase className="h-4 w-4" />
            <span>Find Jobs</span>
          </button>
          <button
            onClick={() => onTabChange('analytics')}
            className={`flex items-center gap-2 rounded-md px-3.5 py-1.5 text-sm font-medium transition-all ${
              activeTab === 'analytics'
                ? 'bg-white text-indigo-600 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <BarChart3 className="h-4 w-4" />
            <span>Platform Analytics</span>
          </button>
        </div>

        {/* System Health Badge */}
        <div className="flex items-center gap-3">
          <div
            className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
              isHealthy
                ? 'bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20'
                : 'bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-600/20'
            }`}
            title={`Database: ${health?.database || 'checking...'}`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                isHealthy ? 'bg-emerald-500' : 'bg-rose-500'
              }`}
            />
            <span className="hidden sm:inline">API:</span>
            <span>{isHealthy ? 'Online' : 'Degraded'}</span>
          </div>

          <button
            onClick={onRefreshHealth}
            disabled={healthLoading}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition"
            title="Refresh system status"
            aria-label="Refresh system status"
          >
            <RefreshCw className={`h-4 w-4 ${healthLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>
    </header>
  );
};
