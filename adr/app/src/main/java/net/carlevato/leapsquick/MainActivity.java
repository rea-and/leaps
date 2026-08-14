package net.carlevato.leapsquick;

import android.app.Activity; import android.os.Bundle; import android.widget.*;

public class MainActivity extends Activity {
  public void onCreate(Bundle state) { super.onCreate(state); setContentView(R.layout.activity_main);
    EditText url=findViewById(R.id.url); TextView status=findViewById(R.id.status);
    url.setText(getSharedPreferences("leaps",0).getString("url","https://carlevato.net/leaps"));
    findViewById(R.id.save).setOnClickListener(v->{ String value=url.getText().toString().replaceAll("/+$",""); getSharedPreferences("leaps",0).edit().putString("url",value).apply(); status.setText("Saved. Add the Leaps Quick Record widget to your home screen."); });
  }
}
