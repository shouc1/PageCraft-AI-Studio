import { SessionWorkspace } from "@/components/session/SessionWorkspace";

export default function SessionDetailPage({
  params
}: {
  params: { id: string };
}) {
  return <SessionWorkspace sessionId={params.id} />;
}