/* Android-specific pieces of Crispy Doom.
 * The ENDOOM DOS text-mode exit screen makes no sense on mobile (it wants its
 * own SDL text window at exit), so it is disabled here. */

#include <string.h>

#include "SDL.h"

#include "doomdef.h"
#include "doomtype.h"
#include "i_system.h"
#include "i_timer.h"
#include "i_video.h"
#include "m_menu.h"
#include "m_misc.h"
#include "net_client.h"
#include "net_defs.h"
#include "net_server.h"

void I_Endoom(unsigned char *data)
{
    (void) data;
}

/* net_gui.c is the DOS-style textscreen lobby, excluded on Android: it wants a
 * terminal we do not have and a player list nobody wants to read on a phone.
 * This is the same wait, drawn with the game's own renderer.
 *
 * The host no longer launches the instant a second player appears. Co-op and
 * deathmatch are worth three or four marines, so the host gathers everybody and
 * then taps the screen to start; clients simply wait for that tap. Both sides
 * still give up after a minute rather than hang on a network that never answers.
 */

#define NET_WAIT_SECONDS 60

void NET_WaitForLaunch(void)
{
    int deadline = I_GetTime() + NET_WAIT_SECONDS * TICRATE;
    boolean startpressed = false;

    while (net_waiting_for_launch)
    {
        SDL_Event ev;
        char line[80];
        int  dots;
        int  num, total;

        NET_CL_Run();
        NET_SV_Run();

        if (!net_client_connected)
        {
            return;
        }

        if (I_GetTime() > deadline)
        {
            NET_CL_Disconnect();
            return;
        }

        // No keyboard at boot, so the host starts the match with a tap. Drain
        // the queue every frame so a stray touch is never left sitting unread.
        SDL_PumpEvents();
        while (SDL_PollEvent(&ev))
        {
            if (ev.type == SDL_QUIT)
            {
                NET_CL_Disconnect();
                return;
            }
            else if (ev.type == SDL_FINGERDOWN || ev.type == SDL_KEYDOWN)
            {
                startpressed = true;
            }
        }

        num = net_client_wait_data.num_players;
        total = net_client_wait_data.max_players;

        // The host holds the only start button and needs a second player before
        // there is anything to start. Three or four can gather first; one tap
        // then launches the map for everybody.
        if (net_client_received_wait_data
         && net_client_wait_data.is_controller
         && num >= 2
         && startpressed)
        {
            NET_CL_LaunchGame();
        }

        dots = (I_GetTime() / (TICRATE / 2)) % 4;

        if (!net_client_received_wait_data)
        {
            M_snprintf(line, sizeof(line), "Looking for a game%.*s", dots, "...");
        }
        else if (!net_client_wait_data.is_controller)
        {
            M_snprintf(line, sizeof(line), "%d of %d -- waiting for host", num, total);
        }
        else if (num < 2)
        {
            M_snprintf(line, sizeof(line), "Waiting for players (%d of %d)", num, total);
        }
        else
        {
            M_snprintf(line, sizeof(line), "%d of %d -- tap to start", num, total);
        }

        memset(I_VideoBuffer, 0,
               SCREENWIDTH * SCREENHEIGHT * sizeof(*I_VideoBuffer));

        M_WriteText(ORIGWIDTH / 2 - M_StringWidth(line) / 2,
                    ORIGHEIGHT / 2 - 4, line);

        I_FinishUpdate();
        I_Sleep(20);
    }
}
