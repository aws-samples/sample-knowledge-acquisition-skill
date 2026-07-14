import { useState } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, useLocation, useParams, Navigate } from 'react-router-dom';
import TopNavigation from '@cloudscape-design/components/top-navigation';
import AppLayout from '@cloudscape-design/components/app-layout';
import SideNavigation, { SideNavigationProps } from '@cloudscape-design/components/side-navigation';
import { AuthProvider, useAuth } from './auth/AuthContext';
import WikiListPage from './pages/WikiListPage';
import DashboardPage from './pages/DashboardPage';
import EntitiesPage from './pages/EntitiesPage';
import ConceptsPage from './pages/ConceptsPage';
import ComparisonsPage from './pages/ComparisonsPage';
import QueriesPage from './pages/QueriesPage';
import GraphPage from './pages/GraphPage';
import LogPage from './pages/LogPage';
import DetailPage from './pages/DetailPage';
import LoginPage from './pages/LoginPage';

function TopNav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div id="top-nav" style={{ position: 'sticky', top: 0, zIndex: 1002 }}>
      <TopNavigation
        identity={{
          href: '/',
          title: 'Knowledge Wiki',
          onFollow: (e) => { e.preventDefault(); navigate('/'); },
        }}
        utilities={[
          {
            type: 'menu-dropdown',
            text: user?.username || 'User',
            description: user?.email || '',
            iconName: 'user-profile',
            items: [
              { id: 'signout', text: 'Sign out' },
            ],
            onItemClick: ({ detail }) => {
              if (detail.id === 'signout') {
                logout();
                navigate('/login');
              }
            },
          },
        ]}
      />
    </div>
  );
}

function WikiLayout() {
  const { wikiName } = useParams<{ wikiName: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [navigationOpen, setNavigationOpen] = useState(true);

  const base = `/w/${wikiName}`;

  const navItems: SideNavigationProps.Item[] = [
    { type: 'link', text: '← All Wikis', href: '/' },
    { type: 'divider' },
    { type: 'link', text: 'Overview', href: base },
    { type: 'divider' },
    { type: 'section-group', title: 'Knowledge Base', items: [
      { type: 'link', text: 'Entities', href: `${base}/entities` },
      { type: 'link', text: 'Concepts', href: `${base}/concepts` },
      { type: 'link', text: 'Comparisons', href: `${base}/comparisons` },
      { type: 'link', text: 'Queries', href: `${base}/queries` },
    ]},
    { type: 'divider' },
    { type: 'link', text: 'Graph', href: `${base}/graph` },
    { type: 'link', text: 'Activity Log', href: `${base}/log` },
  ];

  // Determine active href for highlighting
  const pathAfterBase = location.pathname.replace(base, '') || '/';
  const segment = pathAfterBase.split('/')[1] || '';
  const activeHref = segment ? `${base}/${segment}` : base;

  return (
    <AppLayout
      navigation={
        <SideNavigation
          activeHref={activeHref}
          items={navItems}
          onFollow={(e) => {
            e.preventDefault();
            navigate(e.detail.href);
          }}
        />
      }
      navigationOpen={navigationOpen}
      onNavigationChange={({ detail }) => setNavigationOpen(detail.open)}
      content={
        <Routes>
          <Route path="/" element={<DashboardPage wikiName={wikiName} />} />
          <Route path="/entities" element={<EntitiesPage wikiName={wikiName} />} />
          <Route path="/concepts" element={<ConceptsPage wikiName={wikiName} />} />
          <Route path="/comparisons" element={<ComparisonsPage wikiName={wikiName} />} />
          <Route path="/queries" element={<QueriesPage wikiName={wikiName} />} />
          <Route path="/graph" element={<GraphPage wikiName={wikiName} />} />
          <Route path="/log" element={<LogPage wikiName={wikiName} />} />
          <Route path="/page/:group/:slug" element={<DetailPage wikiName={wikiName} />} />
        </Routes>
      }
      toolsHide={true}
      headerSelector="#top-nav"
    />
  );
}

function AppContent() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return null;
  }

  if (!isAuthenticated && location.pathname !== '/login') {
    return <Navigate to="/login" replace />;
  }

  if (location.pathname === '/login') {
    return <LoginPage />;
  }

  return (
    <>
      <TopNav />
      <Routes>
        <Route path="/" element={
          <AppLayout
            navigationHide={true}
            content={<WikiListPage />}
            toolsHide={true}
            headerSelector="#top-nav"
          />
        } />
        <Route path="/w/:wikiName/*" element={<WikiLayout />} />
        {/* Legacy route redirect */}
        <Route path="/wiki/:group/:slug" element={<LegacyRedirect />} />
      </Routes>
    </>
  );
}

/** Redirect old /wiki/group/slug URLs to /w/<first-wiki>/page/group/slug */
function LegacyRedirect() {
  const { group, slug } = useParams();
  // Redirect to the first wiki — a reasonable default for single-wiki setups
  return <Navigate to={`/w/_default/page/${group}/${slug}`} replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </AuthProvider>
  );
}
