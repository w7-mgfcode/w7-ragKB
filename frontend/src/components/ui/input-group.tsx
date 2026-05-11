import * as React from "react";
import { cn } from "@/lib/utils";
import { Textarea } from "@/components/ui/textarea";

export function InputGroup({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("w-full rounded-md border bg-background", className)} {...props} />;
}

type AddonProps = React.HTMLAttributes<HTMLDivElement> & {
  align?: "block-start" | "block-end";
};

export function InputGroupAddon({
  className,
  align = "block-start",
  ...props
}: AddonProps) {
  return (
    <div
      className={cn(
        "flex px-3",
        align === "block-end" ? "justify-end pb-2 pt-1" : "justify-start pb-1 pt-2",
        className
      )}
      {...props}
    />
  );
}

export function InputGroupText({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex rounded-md border border-border bg-muted px-2 py-1 text-xs text-muted-foreground",
        className
      )}
      {...props}
    />
  );
}

export function InputGroupTextarea({
  className,
  ...props
}: React.ComponentProps<typeof Textarea>) {
  return (
    <Textarea
      className={cn("min-h-[80px] w-full rounded-md border-0 bg-transparent focus-visible:ring-0", className)}
      {...props}
    />
  );
}
