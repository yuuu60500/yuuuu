//+------------------------------------------------------------------+
//| HMI_AlertManager.mqh — flushed in Phase 7 only                   |
//| Historical build never alerts (Spec 17.3).                       |
//+------------------------------------------------------------------+
#ifndef HMI_ALERT_MQH
#define HMI_ALERT_MQH
#include "HMI_ObjectManager.mqh"

void AlertFlush()
  {
   for(int i = 0; i < g_alertq_n; i++)
     {
      if(!g_live || !InpAlertsEnabled) continue;
      string msg = _Symbol + "  " + g_alertq[i];
      if(InpAlertPopup) Alert(msg);
      if(InpAlertPush)  SendNotification(msg);
     }
   g_alertq_n = 0;
  }

#endif // HMI_ALERT_MQH
