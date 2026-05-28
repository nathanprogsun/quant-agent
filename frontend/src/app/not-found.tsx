import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex h-screen items-center justify-center bg-gray-50">
      <div className="max-w-md text-center">
        <h1 className="mb-4 text-6xl font-bold text-gray-200">404</h1>
        <h2 className="mb-4 text-xl font-semibold text-gray-800">
          Page not found
        </h2>
        <p className="mb-6 text-gray-600">
          The page you are looking for does not exist.
        </p>
        <Link
          href="/workspace"
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
        >
          Go to workspace
        </Link>
      </div>
    </div>
  );
}
