import * as React from "react";
import { cn } from "@/lib/utils";

export function FieldGroup({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("space-y-4", className)} {...props} />;
}

export function Field({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("space-y-2", className)} {...props} />;
}

export function FieldLabel({
  className,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn("text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70", className)}
      {...props}
    />
  );
}

export function FieldDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-xs text-muted-foreground", className)} {...props} />;
}

type FieldErrorProps = React.HTMLAttributes<HTMLDivElement> & {
  errors?: Array<{ message?: string } | undefined>;
};

export function FieldError({ className, errors, ...props }: FieldErrorProps) {
  const messages = (errors ?? []).map((e) => e?.message).filter(Boolean) as string[];
  if (messages.length === 0) return null;
  return (
    <div className={cn("text-sm text-destructive", className)} {...props}>
      {messages.map((msg, idx) => (
        <p key={`${msg}-${idx}`}>{msg}</p>
      ))}
    </div>
  );
}
