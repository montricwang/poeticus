import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

type Theme = "light" | "dark" | "system";

const options: { value: Theme; label: string }[] = [
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
  { value: "system", label: "系统" },
];

export function ThemeSwitcher() {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem("poeticus-theme");

    if (saved === "light" || saved === "dark") {
      return saved;
    }

    return "system";
  });

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");

    function applyTheme() {
      const isDark = theme === "dark" || (theme === "system" && media.matches);

      document.documentElement.classList.toggle("dark", isDark);

      // Safari / iPadOS 会用 theme-color 绘制浏览器边缘与弹性回弹区域。
      // 同步实际页面背景，避免深色模式回弹时露出浅色条带。
      const themeColor = document.querySelector<HTMLMetaElement>(
        'meta[name="theme-color"]',
      );
      if (themeColor) {
        themeColor.content = getComputedStyle(
          document.documentElement,
        ).backgroundColor;
      }
    }

    applyTheme();

    media.addEventListener("change", applyTheme);

    return () => {
      media.removeEventListener("change", applyTheme);
    };
  }, [theme]);

  function changeTheme(next: Theme) {
    setTheme(next);
    localStorage.setItem("poeticus-theme", next);
  }

  return (
    <div className="flex gap-1">
      {options.map((option) => (
        <Button
          key={option.value}
          variant={theme === option.value ? "default" : "outline"}
          size="sm"
          onClick={() => changeTheme(option.value)}
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
}
