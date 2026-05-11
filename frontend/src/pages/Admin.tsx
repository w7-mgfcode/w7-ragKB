
import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { UsersTable } from '@/components/admin/UsersTable';
import { ConversationsTable } from '@/components/admin/ConversationsTable';
import { useAdmin } from '@/hooks/useAdmin';
import { Button } from '@/components/ui/button';
import { MessageSquare } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import SystemMonitor from '@/components/admin/SystemMonitor';
import { GatewayManagement } from '@/components/admin/GatewayManagement';
import { DMPairingDashboard } from '@/components/admin/DMPairingDashboard';
import { SecurityAuditLog } from '@/components/admin/SecurityAuditLog';
import { CommandPalette } from '@/components/CommandPalette';

export const Admin = () => {
  const { isAdmin, loading } = useAdmin();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('users');

  useEffect(() => {
    if (!loading && !isAdmin) {
      navigate('/');
    }
  }, [isAdmin, loading, navigate]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="animate-pulse">Loading...</div>
      </div>
    );
  }

  if (!isAdmin) {
    return null;
  }

  return (
    <div className="flex flex-col min-h-screen">
      {/* Command Palette - Global keyboard shortcut */}
      <CommandPalette 
        onNavigate={(tab) => setActiveTab(tab)}
        onOpenDialog={(dialog) => {
          // TODO: Implement dialog opening logic when dialogs are created
          console.log('Open dialog:', dialog);
        }}
      />
      
      <div className="border-b">
        <div className="flex items-center justify-between px-4 py-2">
          <h1 className="text-lg font-semibold">Admin Dashboard</h1>
          <Button variant="outline" size="sm" asChild>
            <Link to="/">
              <MessageSquare className="mr-2 h-4 w-4" />
              Back to Chat
            </Link>
          </Button>
        </div>
      </div>
      <div className="flex-1 overflow-auto p-4">
        <div className="flex justify-center mb-6">
          <Tabs 
            defaultValue="users" 
            value={activeTab} 
            onValueChange={setActiveTab}
            className="w-full max-w-[95%] lg:max-w-[1200px]"
          >
            <div className="flex justify-center mb-6">
              <TabsList className="grid w-[800px] grid-cols-6 bg-gray-100 dark:bg-gray-800">
                <TabsTrigger 
                  value="users" 
                  className="transition-all data-[state=active]:bg-blue-500 data-[state=active]:text-white"
                >
                  Users
                </TabsTrigger>
                <TabsTrigger 
                  value="conversations" 
                  className="transition-all data-[state=active]:bg-blue-500 data-[state=active]:text-white"
                >
                  Conversations
                </TabsTrigger>
                <TabsTrigger 
                  value="system" 
                  className="transition-all data-[state=active]:bg-blue-500 data-[state=active]:text-white"
                >
                  System
                </TabsTrigger>
                <TabsTrigger
                  value="gateway"
                  className="transition-all data-[state=active]:bg-blue-500 data-[state=active]:text-white"
                >
                  Gateway
                </TabsTrigger>
                <TabsTrigger
                  value="dm-pairing"
                  className="transition-all data-[state=active]:bg-blue-500 data-[state=active]:text-white"
                >
                  DM Pairing
                </TabsTrigger>
                <TabsTrigger
                  value="security"
                  className="transition-all data-[state=active]:bg-blue-500 data-[state=active]:text-white"
                >
                  Security
                </TabsTrigger>
              </TabsList>
            </div>
            
            <TabsContent value="users" className="mt-0">
              <UsersTable />
            </TabsContent>
            
            <TabsContent value="conversations" className="mt-0">
              <div className="p-4">
                <h2 className="text-2xl font-semibold mb-4">Conversation Management</h2>
                <ConversationsTable />
              </div>
            </TabsContent>
            
            <TabsContent value="system" className="mt-0">
              <SystemMonitor />
            </TabsContent>
            
            <TabsContent value="gateway" className="mt-0">
              <GatewayManagement />
            </TabsContent>

            <TabsContent value="dm-pairing" className="mt-0">
              <DMPairingDashboard />
            </TabsContent>

            <TabsContent value="security" className="mt-0">
              <SecurityAuditLog />
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
};

export default Admin;
