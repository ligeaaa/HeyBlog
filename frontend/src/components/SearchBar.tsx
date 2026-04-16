import { useState } from "react";
import { Search } from "lucide-react";

interface SearchBarProps {
  onSearch: (url: string) => void;
  isLoading?: boolean;
}

/**
 * Render the example search box used to look up a blog URL.
 *
 * @param onSearch Callback triggered with the trimmed URL.
 * @param isLoading Whether the search action is currently pending.
 * @returns Search form UI.
 */
export function SearchBar({ onSearch, isLoading = false }: SearchBarProps) {
  const [inputValue, setInputValue] = useState("");

  /**
   * Submit the current query when non-empty.
   *
   * @param event Form submit event.
   */
  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (inputValue.trim()) {
      onSearch(inputValue.trim());
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mx-auto w-full max-w-3xl">
      <div className="relative">
        <input
          type="text"
          value={inputValue}
          onChange={(event) => setInputValue(event.target.value)}
          placeholder="输入博客URL进行搜索..."
          className="w-full rounded-lg border-2 border-gray-200 px-6 py-4 pr-14 text-lg transition-colors focus:border-blue-500 focus:outline-none"
          disabled={isLoading}
        />
        <button
          type="submit"
          aria-label="搜索博客 URL"
          disabled={isLoading || !inputValue.trim()}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md bg-blue-500 p-2 text-white transition-colors hover:bg-blue-600 disabled:cursor-not-allowed disabled:bg-gray-300"
        >
          <Search className="h-6 w-6" />
        </button>
      </div>
    </form>
  );
}
