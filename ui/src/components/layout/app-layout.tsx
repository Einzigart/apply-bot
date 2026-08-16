import { Outlet } from "react-router";
import { Sidebar } from "./sidebar";

export function AppLayout() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-white text-neutral-900 font-sans">
      <Sidebar />
      <main className="flex-1 flex flex-col h-screen overflow-y-auto bg-white px-8 py-6">
        <div className="max-w-5xl mx-auto w-full">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
