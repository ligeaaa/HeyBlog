import { ReactNode } from "react";

type Props = {
  title: string;
  note?: string;
  children: ReactNode;
};

export function Surface({ title, note, children }: Props) {
  return (
    <section className="surface-card">
      <div className="surface-head">
        <h3>{title}</h3>
        {note ? <span>{note}</span> : null}
      </div>
      {children}
    </section>
  );
}
