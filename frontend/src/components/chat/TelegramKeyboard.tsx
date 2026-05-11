import { Button } from '@/components/ui/button';
import { ExternalLink } from 'lucide-react';

interface TelegramButton {
  text: string;
  callback_data?: string;
  url?: string;
}

interface TelegramKeyboardProps {
  buttons: Array<Array<TelegramButton>>;
  onButtonClick?: (callbackData: string) => void;
}

export const TelegramKeyboard = ({
  buttons,
  onButtonClick,
}: TelegramKeyboardProps) => {
  const handleClick = (button: TelegramButton) => {
    if (button.url) {
      window.open(button.url, '_blank', 'noopener,noreferrer');
    } else if (button.callback_data && onButtonClick) {
      onButtonClick(button.callback_data);
    }
  };

  return (
    <div className="flex flex-col gap-1 mt-2">
      {buttons.map((row, rowIndex) => (
        <div key={rowIndex} className="flex gap-1">
          {row.map((button, btnIndex) => (
            <Button
              key={btnIndex}
              variant="outline"
              size="sm"
              className="flex-1 px-2 py-1 h-auto text-xs"
              onClick={() => handleClick(button)}
            >
              <span className="truncate">{button.text}</span>
              {button.url && <ExternalLink className="h-3 w-3 ml-1 shrink-0" />}
            </Button>
          ))}
        </div>
      ))}
    </div>
  );
};
