import { SharePageClient } from "./SharePageClient";

export default async function SharePage({
  params,
}: {
  params: Promise<{ share_id: string }>;
}) {
  const { share_id } = await params;
  return <SharePageClient shareId={share_id} />;
}
