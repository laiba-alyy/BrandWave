import DashRouteSkeleton from '@/components/dashboard/DashRouteSkeleton'

// Ye route dash.css par hai, is liye Suspense fallback bhi usi palette ka.
export default function Loading() {
  return <DashRouteSkeleton />
}
