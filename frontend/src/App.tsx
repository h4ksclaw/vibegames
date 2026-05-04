import React, { useEffect, useRef, useState } from 'react';
import { ThemeProvider, Container } from '@mui/material';
import { Game } from './types/game';
import theme from './theme';
import axios from 'axios';
import { TopAppBar } from './components/AppBar';
import { GameGrid } from './components/GameGrid';
import { GameView } from './components/GameView';
import { Sidebar } from './components/Sidebar';
import { SortByOptions } from './types/api';

const getFavoriteGames = () => {
  const fav = localStorage.getItem('favoriteGames');
  if (fav) return JSON.parse(fav);
  return [];
};

const storageFavoriteGames = (games: Game[]) => {
  localStorage.setItem('favoriteGames', JSON.stringify(games));
}

const App: React.FC = () => {
  const [games, setGames] = useState<Game[]>([]);
  const [searchTerm, setSearchTerm] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('search');
  });
  const [sortBy, setSortBy] = useState<SortByOptions>(() => {
    const params = new URLSearchParams(window.location.search);
    return (params.get('sort') as SortByOptions) || 'date_added';
  });
  const [selectedGame, setSelectedGame] = useState<Game | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [favoriteSearch, setFavoriteSearch] = useState('');
  const [favorites, setFavorites] = useState<Game[]>(getFavoriteGames());
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const scrollRef = useRef(0);

  const fetchGames = async () => {
    const res = await axios.get<Game[]>(`${process.env.REACT_APP_API_URL}/api/games`, {
      params: {
        sort_by: sortBy,
        search_query: searchTerm || undefined,
        page: page,
      }
    });
    if (page === 1) {
      setGames(res.data);
    } else {
      setGames((prev) => [...prev, ...res.data]);
    }
    if (res.data.length < 20) {
      setHasMore(false);
    }
  };

  useEffect(() => {
    setPage(1);
    setHasMore(true);
  }, [searchTerm]);

  useEffect(() => {
    fetchGames();
    setFavorites(getFavoriteGames());
  }, [sortBy, searchTerm, page]);

  const addFavorite = (game: Game) => {
    const updated = [...favorites, game];
    // Avoid duplicates
    const unique = updated.filter((g, index, self) =>
      index === self.findIndex((t) => t.project === g.project)
    );
    setFavorites(unique);
    storageFavoriteGames(unique);
  };

  const handleGameClick = (game: Game) => {
    scrollRef.current = window.scrollY;
    setSelectedGame(game);
  };

  useEffect(() => {
    if (!selectedGame && scrollRef.current) {
      window.scrollTo(0, scrollRef.current);
      scrollRef.current = 0;
    }
  }, [selectedGame]);

  return (
    <ThemeProvider theme={theme} >
      <TopAppBar
        initialSearch={searchTerm}
        onSearch={setSearchTerm}
        onSortChange={setSortBy}
        sortBy={sortBy}
        openDrawer={() => setDrawerOpen(true)}
      />
      <Sidebar
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        favorites={favorites}
        search={favoriteSearch}
        setSearch={setFavoriteSearch}
        onDeleteFavorite={(game) => {
          const updated = favorites.filter((g) => g.project !== game.project);
          setFavorites(updated);
          storageFavoriteGames(updated);
        }}
      />
      <Container sx={{ mt: 2 }}>
        {selectedGame ? (
          <GameView game={selectedGame} onBack={() => setSelectedGame(null)} />
        ) : (
          <GameGrid
            games={games}
            onGameClick={handleGameClick}
            favoriteGames={favorites}
            onFavorite={addFavorite}
            hasMore={hasMore}
            onBottomReached={() => setPage((prev) => prev + 1)}
          />
        )}
      </Container>
    </ThemeProvider>
  );
};

export default App;
