import { ReactNode } from "react";

type Props = {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
};

export function PageHeader({ eyebrow, title, description, actions }: Props) {
  return (
    <header className="page-header">
      <div className="page-header-main">
        <p className="eyebrow">{eyebrow}</p>
        <div className="page-header-title-row">
          <h2>{title}</h2>
        </div>
        <p className="page-copy">{description}</p>
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}
