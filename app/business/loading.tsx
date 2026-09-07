import DashRouteSkeleton from '@/components/dashboard/DashRouteSkeleton'

// Dashboard ab dash.css par hai, is liye uska Suspense fallback bhi usi
// palette ka — warna har navigation par safed flash dikhta tha.
export default function Loading() {
  return <DashRouteSkeleton />
}
