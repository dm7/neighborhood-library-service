"use client";

export function StatusBanner(props: {
  error?: string | null;
  success?: string | null;
}) {
  if (props.error) {
    return <div className="message error">{props.error}</div>;
  }
  if (props.success) {
    return <div className="message ok">{props.success}</div>;
  }
  return null;
}
