import { useId, useState } from "react";
import { Edit3, Ellipsis, KeyRound, LucideIcon, RotateCcw, Trash2 } from "lucide-react";

type UserRowActionsProps = {
  userName: string;
  isActive: boolean;
  isSelf: boolean;
  onEdit: () => void;
  onResetPassword: () => void;
  onDeactivate: () => void;
  onActivate: () => void;
};

type RowAction = {
  key: string;
  label: string;
  icon: LucideIcon;
  hoverClass: string;
  disabled?: boolean;
  title?: string;
  onSelect: () => void;
};

// Desktop shows icon buttons inline; phones collapse them into a "⋯" menu.
export function UserRowActions({
  userName,
  isActive,
  isSelf,
  onEdit,
  onResetPassword,
  onDeactivate,
  onActivate,
}: UserRowActionsProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuId = useId();

  const actions: RowAction[] = [
    { key: "edit", label: "Edit role / user details", icon: Edit3, hoverClass: "hover:text-blue-600 hover:bg-blue-50", onSelect: onEdit },
    { key: "reset", label: "Reset password", icon: KeyRound, hoverClass: "hover:text-amber-600 hover:bg-amber-50", onSelect: onResetPassword },
    isActive
      ? {
          key: "deactivate",
          label: "Deactivate user",
          icon: Trash2,
          hoverClass: "hover:text-rose-600 hover:bg-rose-50",
          disabled: isSelf,
          title: isSelf ? "Cannot deactivate yourself" : undefined,
          onSelect: onDeactivate,
        }
      : {
          key: "activate",
          label: "Activate user",
          icon: RotateCcw,
          hoverClass: "hover:text-emerald-600 hover:bg-emerald-50",
          onSelect: onActivate,
        },
  ];

  return (
    <>
      <div className="hidden items-center justify-end gap-2 sm:flex">
        {actions.map((action) => {
          const Icon = action.icon;
          return (
            <button
              key={action.key}
              type="button"
              onClick={action.onSelect}
              disabled={action.disabled}
              title={action.title}
              aria-label={`${action.label}: ${userName}`}
              className={`inline-flex h-11 w-11 items-center justify-center rounded-lg transition-colors ${
                action.disabled
                  ? "cursor-not-allowed text-slate-300"
                  : `cursor-pointer text-slate-400 ${action.hoverClass}`
              }`}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
            </button>
          );
        })}
      </div>

      <div
        className="flex flex-col items-end sm:hidden"
        onKeyDown={(event) => {
          if (event.key === "Escape") setIsMenuOpen(false);
        }}
      >
        <button
          type="button"
          onClick={() => setIsMenuOpen((open) => !open)}
          aria-label={`More actions for ${userName}`}
          aria-expanded={isMenuOpen}
          aria-controls={isMenuOpen ? menuId : undefined}
          className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100"
        >
          <Ellipsis className="h-5 w-5" aria-hidden="true" />
        </button>
        {isMenuOpen && (
          <ul id={menuId} className="mt-2 flex w-56 flex-col gap-1 rounded-lg border border-slate-200 bg-white p-1 text-left shadow-sm">
            {actions.map((action) => {
              const Icon = action.icon;
              return (
                <li key={action.key}>
                  <button
                    type="button"
                    disabled={action.disabled}
                    onClick={() => {
                      setIsMenuOpen(false);
                      action.onSelect();
                    }}
                    className={`flex min-h-11 w-full items-center gap-2 rounded-md px-3 text-sm ${
                      action.disabled ? "cursor-not-allowed text-slate-300" : "text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    <Icon className="h-4 w-4" aria-hidden="true" />
                    {action.label}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
}
