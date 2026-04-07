import { ReactNode } from "react";

type Props = {
  title: string;
  note?: string;
  children: ReactNode;
  variant?: "standard" | "muted" | "danger";
};

export function Surface({ title, note, children, variant = "standard" }: Props) {
  return (
    <section className={`surface-card surface-${variant}`}>
      <div className="surface-head">
        <h3>{title}</h3>
        {note ? <span>{note}</span> : null}
      </div>
      {children}
    </section>
  );
}
