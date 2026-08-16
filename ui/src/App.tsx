import { createBrowserRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppLayout } from "./components/layout/app-layout";
import { DashboardPage } from "./pages/dashboard";
import { JobsPage } from "./pages/jobs";
import { ApplicationsPage } from "./pages/applications";
import { RunsPage } from "./pages/runs";
import { RunDetailPage } from "./pages/run-detail";
import { ProfilePage } from "./pages/profile";
import { SettingsPage } from "./pages/settings";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      retry: 1,
    },
  },
});

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "jobs", element: <JobsPage /> },
      { path: "applications", element: <ApplicationsPage /> },
      { path: "runs", element: <RunsPage /> },
      { path: "runs/:id", element: <RunDetailPage /> },
      { path: "profile", element: <ProfilePage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
export default App;
