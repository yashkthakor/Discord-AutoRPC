/**
 * InsetList (A17 / D-036): the single list pattern used by App Names, Taglines,
 * Ignored Apps and the whitelist.
 *
 * - filter field above, `+` / `−` bar below
 * - adding opens a popover, not a modal
 * - removal works from the `−` button and the `Delete` key
 * - empty states are real, not blank space
 */

import { useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Inbox, Minus, Plus, Search, Trash2 } from "lucide-react";
import { Button, IconButton } from "./Button";
import { SearchInput } from "./Inputs";
import { Popover } from "./Overlay";
import { EmptyState } from "./Structure";

export interface InsetListProps<T> {
  ariaLabel: string;
  items: T[];
  getKey: (item: T) => string;
  filterText: (item: T) => string;
  renderRow: (item: T) => ReactNode;
  emptyTitle: string;
  emptyHint?: ReactNode;
  /** When omitted, removal is not offered. */
  onRemove?: (item: T) => void;
  removeLabel?: string;
  /** Renders the add form inside a popover. Receives `close`. */
  renderAdd?: (close: () => void) => ReactNode;
  addLabel?: string;
  addDisabled?: boolean;
  filterPlaceholder?: string;
  footnote?: ReactNode;
}

export function InsetList<T>({
  ariaLabel,
  items,
  getKey,
  filterText,
  renderRow,
  emptyTitle,
  emptyHint,
  onRemove,
  removeLabel = "Remove",
  renderAdd,
  addLabel = "Add",
  addDisabled = false,
  filterPlaceholder = "Filter",
  footnote,
}: InsetListProps<T>) {
  const [filter, setFilter] = useState("");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const rowsRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const query = filter.trim().toLowerCase();
    if (!query) return items;
    return items.filter((item) => filterText(item).toLowerCase().includes(query));
  }, [items, filter, filterText]);

  const selected = filtered.find((item) => getKey(item) === selectedKey) ?? null;

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if ((event.key === "Delete" || event.key === "Backspace") && selected && onRemove) {
      event.preventDefault();
      onRemove(selected);
      setSelectedKey(null);
    }
  };

  return (
    <div className="inset-list">
      <div className="inset-list__toolbar">
        <SearchInput
          value={filter}
          onChange={setFilter}
          placeholder={filterPlaceholder}
          ariaLabel={`Filter ${ariaLabel}`}
          icon={<Search size={14} aria-hidden="true" />}
        />
        <span className="t-caption t-numeric">
          {filtered.length === items.length
            ? `${items.length}`
            : `${filtered.length} of ${items.length}`}
        </span>
      </div>

      <div
        className="inset-list__rows"
        role="listbox"
        aria-label={ariaLabel}
        tabIndex={0}
        ref={rowsRef}
        onKeyDown={handleKeyDown}
      >
        {filtered.length === 0 ? (
          <EmptyState
            icon={<Inbox size={22} aria-hidden="true" />}
            title={items.length === 0 ? emptyTitle : "No matches"}
            hint={items.length === 0 ? emptyHint : "Try a different filter."}
          />
        ) : (
          filtered.map((item) => {
            const key = getKey(item);
            const isSelected = key === selectedKey;
            return (
              <div
                key={key}
                className="inset-list__row"
                role="option"
                aria-selected={isSelected}
                onClick={() => setSelectedKey(isSelected ? null : key)}
                onDoubleClick={() => rowsRef.current?.focus()}
              >
                <div className="inset-list__main">{renderRow(item)}</div>
                {onRemove ? (
                  <div className="inset-list__actions">
                    <IconButton
                      label={`${removeLabel}: ${key}`}
                      tone="danger"
                      icon={<Trash2 size={15} aria-hidden="true" />}
                      onClick={(event) => {
                        event.stopPropagation();
                        onRemove(item);
                      }}
                    />
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </div>

      <div className="inset-list__bar">
        {renderAdd ? (
          <div className="popover-anchor">
            <Button
              variant="secondary"
              size="sm"
              icon={<Plus size={14} aria-hidden="true" />}
              disabled={addDisabled}
              aria-expanded={addOpen}
              onClick={() => setAddOpen((open) => !open)}
            >
              {addLabel}
            </Button>
            <Popover open={addOpen} onClose={() => setAddOpen(false)} labelledBy={`${ariaLabel}-add`}>
              {renderAdd(() => setAddOpen(false))}
            </Popover>
          </div>
        ) : null}

        {onRemove ? (
          <Button
            variant="secondary"
            size="sm"
            icon={<Minus size={14} aria-hidden="true" />}
            disabled={!selected}
            onClick={() => {
              if (!selected) return;
              onRemove(selected);
              setSelectedKey(null);
            }}
          >
            {removeLabel}
          </Button>
        ) : null}
      </div>

      {footnote}
    </div>
  );
}
